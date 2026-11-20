# Quartz — Public contracts of the initial milestone (CONTRACTS)

> Quartz — author: **D1on1n**. **Normative** document. Date: 2026-10-22.
> This file is the **single source of truth** among parallel implementers: each task implements
> exactly the modules it owns (§0.4) and consumes modules from other tasks **only** by the
> names and behaviors described here. Decisions and rationale: [`ARCHITECTURE.md`](ARCHITECTURE.md).
> Prose in English; code, identifiers and error messages in English.
>
> Keywords: **MUST** (mandatory), **MUST NOT** (forbidden), **MAY** (optional).
> Marks: **[O]** behavior observed in Blender 5.2.2 (dump or judge probe); **[I]** inference
> that a future golden may correct (implement as written; if a golden contradicts it, the golden prevails).

---

## 0. General conventions

### 0.1 Files

1. No `.py` file in the project (including `tests/`, `tools/`, `compat/` and fixtures) contains comments or
   docstrings. `from __future__ import ...`, if any, is the first statement.
   This replaces the earlier rule (one-line docstring plus `# Quartz - author: D1on1n`), dropped on 2026-11-12.
2. Identifiers in English. Human documents (`README.md`, `docs/*.md`) in English.
3. Python ≥ 3.13 (the `.venv` is 3.14.7). Dependencies: stdlib + numpy (+ pytest only in tests).
4. No import side effects beyond the registrations explicitly described in this contract
   (e.g. `register_id_type(...)` at the end of `quartz/types/mesh.py`).
5. Disk writes only inside `D:/Claude/reverseEngineering/Quartz`. The default user directory is
   `<root>/tmp/quartz_user` (§1.2.7). Tests write only to `tmp_path` (which `conftest.py` places in
   `<root>/tmp/pytest/…`).
6. No `print` in library code, except where this contract mandates printing (operator reports,
   handler/draw tracebacks, registration warnings), always to `sys.stdout`/`sys.stderr`.

### 0.2 Cross-cutting rules

- **Float32 at rest**: every stored `FLOAT` value (RNA props, `quartz.math` components, `FLOAT*`
  geometry arrays) is `float32`; reads return a Python `float` with the `float32` value
  (`0.1` read back is `0.10000000149011612` **[O]**). Internal computation in `float64`.
- **`q_` prefix**: every public member that is **Quartz-only** on bpy-shaped types (ID, Object, Mesh,
  Struct, Event…) has the `q_` prefix (e.g. `Mesh.q_geometry`, `Attribute.q_array()`); internal members
  use `_q_`. Names without the prefix are reserved for the Blender surface.
- **Exceptions**: use the classes from `quartz.errors` (§1.3); each one inherits from the builtin that Blender
  raises. Messages MUST contain the fragments quoted in this contract; the rest of the wording
  is free (clean-room). Tests check **type** + fragments, never the full text.
- **API prefix in messages**: where a message cites `bpy.ops`/`bpy.data`, use
  `quartz.app.settings.settings.api_prefix` (`"quartz"` by default, `"bpy"` with compat active).
- **Determinism**: no randomness without a seed; no data structure depends on the clock.
- **Thread-safety**: not required (everything is single-threaded).

### 0.3 Glossary

- *Built-in type*: Quartz class decorated with `@builtin_struct` (§1.6.7), with its own `bl_rna` since
  import (e.g. `Object`, `Mesh`, `Operator`).
- *Registrable class*: user subclass of a base with `_q_registrable = True` (`Operator`, `Panel`,
  `Menu`, `Header`, `UIList`, `PropertyGroup`, `AddonPreferences`, inert bases §2.5.5).
- *RNA name*: identifier under which the class appears in `quartz.types`/`bpy.types`
  (operator `"mod.name"` → `"MOD_OT_name"`).
- *Session*: the single `quartz.session.Session` of the process (data, WM, preferences, context, undo).

### 0.4 File owners (task → files)

Each file has exactly **one** owner. No task creates, edits or deletes another task's file.

| Task | Files (relative to the root) |
|---|---|
| `l1-scaffold-app` | `pyproject.toml`, `tests/conftest.py`, `quartz/__init__.py`, `quartz/_version.py`, `quartz/__main__.py`, `quartz/path.py`, `quartz/app/__init__.py`, `quartz/app/handlers.py`, `quartz/app/timers.py`, `quartz/app/msgbus.py`, `quartz/app/translations.py`, `quartz/app/settings.py`, `quartz/app/paths.py`, `tests/arch/test_headers.py`, `tests/arch/test_layering.py`, `tests/arch/test_cleanroom.py`, `tests/unit/test_path.py`, `tests/unit/app/*.py` |
| `l1-math` | `quartz/math/*.py`, `tests/unit/math/*.py` |
| `l1-rna-props` | `quartz/errors.py`, `quartz/props.py`, `quartz/rna/*.py`, `tests/unit/rna/*.py` |
| `l1-geometry` | `quartz/geometry/*.py`, `tests/unit/geometry/*.py` |
| `l2-idmodel` | `quartz/types/__init__.py`, `quartz/types/naming.py`, `quartz/types/id.py`, `quartz/types/blenddata.py`, `quartz/types/object.py`, `quartz/types/collection.py`, `quartz/types/scene.py`, `quartz/types/world.py`, `quartz/types/wm.py`, `quartz/depsgraph.py`, `tests/unit/types/test_naming.py`, `tests/unit/types/test_id.py`, `tests/unit/types/test_blenddata.py`, `tests/unit/types/test_object_transform.py`, `tests/unit/types/test_object_misc.py`, `tests/unit/types/test_collection.py`, `tests/unit/types/test_scene_viewlayer.py`, `tests/unit/types/test_world_wm.py`, `tests/unit/types/test_depsgraph.py` |
| `l2-datablocks` | `quartz/types/mesh.py`, `quartz/types/material.py`, `quartz/types/camera.py`, `quartz/types/light.py`, `quartz/types/image.py`, `quartz/types/text.py`, `tests/unit/types/test_mesh_api.py`, `tests/unit/types/test_mesh_foreach.py`, `tests/unit/types/test_mesh_attributes.py`, `tests/unit/types/test_material_camera.py`, `tests/unit/types/test_light.py`, `tests/unit/types/test_image_text.py`, `tests/unit/types/test_datablock_schema.py` |
| `l2-registry-ui` | `quartz/registry.py`, `quartz/types/operator.py`, `quartz/types/ui.py`, `quartz/types/prefs.py`, `quartz/types/stubs.py`, `quartz/ui.py`, `quartz/utils/__init__.py`, `quartz/utils/previews.py`, `quartz/utils/units.py`, `tests/unit/registry/*.py` |
| `l2-runtime` | `quartz/session.py`, `quartz/contexts.py`, `quartz/ops.py`, `quartz/undo.py`, `quartz/io/__init__.py`, `quartz/io/state.py`, `quartz/io/qzfile.py`, `quartz/testing.py`, `tests/unit/runtime/*.py` |
| `l2-operators` | `quartz/operators/*.py`, `tests/unit/operators/*.py` |
| `l3-compat-bpy` | `quartz/compat/__init__.py`, `quartz/compat/profile.py`, `quartz/compat/blender_5_2.json`, `tools/gen_compat_profile.py`, `compat/bpy/**`, `compat/idprop/**`, `compat/rna_prop_ui.py`, `compat/bl_math.py`, `compat/bl_ui/**`, `compat/bl_operators/**`, `docs/COMPAT.md`, `tests/compat/test_activate.py`, `tests/compat/test_identity.py`, `tests/compat/test_types_view.py`, `tests/compat/test_props_filter.py`, `tests/compat/test_app_shim.py`, `tests/compat/test_usage_surface.py`, `tests/contract/*.py`, `tests/arch/test_compat_thin.py` |
| `l3-compat-math-extras` | `quartz/extras/*.py`, `compat/mathutils/**`, `compat/bpy_extras/**`, `compat/gpu/**`, `compat/gpu_extras/**`, `compat/blf.py`, `compat/aud.py`, `tests/extras/*.py`, `tests/compat/test_mathutils_shim.py`, `tests/compat/test_bpy_extras_shim.py`, `tests/compat/test_gpu_blf_stubs.py` |
| `l3-bmesh` | `quartz/bmesh/*.py`, `compat/bmesh/**`, `tests/bmesh/*.py`, `tests/compat/test_bmesh_shim.py` |
| `l3-addons` | `quartz/addons/*.py`, `compat/addon_utils.py`, `tests/addons/*.py`, `tests/fixtures/addons/**`, `tests/fixtures/extensions/**`, `tests/fixtures/native/**` |
| `l3-cli-sweep` | `quartz/cli.py`, `quartz/sweep.py`, `quartz/scan.py`, `tools/golden_runner.py`, `tools/run_golden.py`, `tools/blender_sweep_baseline.py`, `tools/run_blender_baseline.py`, `tests/golden/**`, `data/golden/**`, `data/sweep/**`, `tests/cli/*.py`, `tests/sweep/*.py`, `tests/fixtures/scripts/**`, `README.md`, `docs/ROADMAP.md` |

Files that already exist and belong to **no** task (do not edit): `tools/scan_bpy_usage.py`,
`tools/dump_bpy_api.py`, `tools/run_dump_bpy_api.ps1`, `tools/probe_judge_facts.py`,
`tests/test_scan_bpy_usage.py`, `data/blender_api_dump.json`, `data/bpy_usage.json`,
`data/blender_facts_judge.json`, `docs/research/*`, `docs/design/*`, `docs/ARCHITECTURE.md`,
`docs/CONTRACTS.md`.

### 0.5 Import rules

Those of ARCHITECTURE §4.2, verified by `tests/arch/test_layering.py` (§1.7). Summary: L1 has four
isolated groups (`app` = `quartz._version`, `quartz.path`, `quartz.app.*`; `rna` = `quartz.errors`,
`quartz.props`, `quartz.rna.*`; `math` = `quartz.math.*`; `geometry` = `quartz.geometry.*`); L2 imports
L1 + L2; L3 imports any `quartz.*`; `compat/**` imports stdlib, `quartz.*` and other shims, **never
numpy**. `quartz/__init__.py` only imports `quartz._version` at module level.

### 0.6 Dependencies within a layer

- L1: none.
- L2: `l2-datablocks` uses `quartz.types.id`, `quartz.types.blenddata`, `quartz.types.object`
  (`register_object_data_type`, `Object` for pointers) from `l2-idmodel`. `l2-registry-ui` uses only L1
  (and, lazily inside functions, `quartz.session`/`quartz.contexts`). `l2-runtime` uses all
  the other L2 tasks. `l2-operators` uses all the other L2 tasks.
- L3: `l3-addons` uses `quartz.compat` (from `l3-compat-bpy`) only for Blender add-ons;
  `l3-cli-sweep` uses all the other L3 tasks.
- A task whose test needs a sibling module that does not exist yet MUST write the test anyway
  (it will pass at the layer gate) and MUST NOT create the sibling's file. Whenever possible, isolate your
  own code with test-local fake owners/types.

---

## 1. Layer 1 — Foundations

### 1.1 Scaffold (`l1-scaffold-app`)

#### 1.1.1 `pyproject.toml` (exact content, except key order)

```toml
[project]
name = "quartz"
version = "0.1.0"
description = "Quartz - headless 3D application core (Cinema 4D x Blender fusion), milestone 1"
authors = [{ name = "D1on1n" }]
requires-python = ">=3.13"
dependencies = ["numpy"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "--import-mode=importlib"
markers = [
    "slow: slow test (still runs by default)",
    "blender: needs the Blender executable; runs only with QUARTZ_RUN_BLENDER=1",
    "sweep: add-on sweep over the Blender scripts corpus; runs only with QUARTZ_RUN_SWEEP=1",
    "corpus: reads the Blender scripts directory (read-only); skipped when missing",
]
```

No `[build-system]`: the project is not installed; it runs from the root.

#### 1.1.2 `tests/conftest.py`

Module constants: `PROJECT_ROOT: Path` (parent of `tests/`), `BLENDER_EXE: Path` (env
`QUARTZ_BLENDER_EXE` or `C:/Program Files/Blender Foundation/Blender 5.2/blender.exe`),
`BLENDER_SCRIPTS: Path` (env `QUARTZ_BLENDER_SCRIPTS` or
`C:/Program Files/Blender Foundation/Blender 5.2/5.2/scripts`), `DUMP_PATH`, `USAGE_PATH`, `FACTS_PATH`
(`data/blender_api_dump.json`, `data/bpy_usage.json`, `data/blender_facts_judge.json`),
`FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"`.

Hooks:

```python
def pytest_configure(config) -> None
    # if config.option.basetemp is None: config.option.basetemp = str(PROJECT_ROOT/"tmp"/"pytest"/f"run-{os.getpid()}")
def pytest_collection_modifyitems(config, items) -> None
    # "blender": skip unless os.environ.get("QUARTZ_RUN_BLENDER") == "1" and BLENDER_EXE.exists()
    # "sweep":   skip unless os.environ.get("QUARTZ_RUN_SWEEP") == "1" and BLENDER_SCRIPTS.exists()
    # "corpus":  skip unless BLENDER_SCRIPTS.exists()
```

Fixtures (all import `quartz` **inside** the function, so that L1 tests do not load L2/L3):

| Fixture | Scope | Does / returns |
|---|---|---|
| `project_root` | session | `PROJECT_ROOT` |
| `fixtures_dir` | session | `FIXTURES_DIR` |
| `blender_dump` | session | `dict` loaded from `DUMP_PATH` |
| `blender_usage` | session | `dict` from `USAGE_PATH` |
| `blender_facts` | session | `dict` from `FACTS_PATH` |
| `blender_exe` | function | `BLENDER_EXE` or `pytest.skip` |
| `blender_scripts` | function | `BLENDER_SCRIPTS` or `pytest.skip` |
| `qz_user_dir` | function | `monkeypatch.setenv("QUARTZ_USER_DIR", str(tmp_path / "quartz_user"))`; calls `quartz.app.paths.reset()` before and after; returns the `Path` |
| `qz` | function | uses `qz_user_dir`; `with quartz.testing.isolated(template="default") as s: yield s` |
| `qz_empty` | function | same with `template="empty"` |
| `bpy` | function | uses `qz`; `quartz.compat.activate(strict=True)`; `yield importlib.import_module("bpy")`; at the end `quartz.compat.deactivate()` |
| `bpy_lenient` | function | same with `strict=False` |

#### 1.1.3 `quartz/_version.py`

```python
VERSION: tuple[int, int, int] = (0, 1, 0)
__version__: str = "0.1.0"
APP_NAME: str = "Quartz"
AUTHOR: str = "D1on1n"
```

#### 1.1.4 `quartz/__init__.py` (lazy facade, PEP 562)

```python
from quartz._version import VERSION, __version__, APP_NAME, AUTHOR   # only module-level import

LAZY_SUBMODULES: frozenset[str] = frozenset({
    "addons", "app", "bmesh", "cli", "compat", "contexts", "depsgraph", "errors", "extras",
    "geometry", "io", "math", "operators", "ops", "path", "props", "registry", "rna", "scan",
    "session", "sweep", "testing", "types", "ui", "undo", "utils",
})

def __getattr__(name: str) -> object:
    # "data"    -> quartz.session.api_data()      (evaluated on EVERY access; never stored in the module)
    # "context" -> quartz.session.api_context()   (same)
    # "msgbus"  -> importlib.import_module("quartz.app.msgbus")
    # name in LAZY_SUBMODULES -> importlib.import_module(f"quartz.{name}")
    # otherwise: AttributeError(f"module 'quartz' has no attribute '{name}'")
def __dir__() -> list[str]   # sorted(LAZY_SUBMODULES | {"data", "context", "msgbus", "VERSION", "__version__", "APP_NAME", "AUTHOR"})
```

`quartz/__init__.py` MUST NOT assign `data`/`context` as module attributes (the RestrictBlend
swap depends on always going through `__getattr__`).

#### 1.1.5 `quartz/__main__.py`

```python
if __name__ == "__main__":
    from quartz.cli import main
    raise SystemExit(main())
```

#### 1.1.6 `quartz/path.py` (= `bpy.path`)

```python
def set_blend_filepath_provider(fn: Callable[[], str] | None) -> None   # installed by quartz.session; None restores the default (lambda: "")
def blend_filepath() -> str
def abspath(path: str, *, start: str | None = None, library: object = None) -> str
def relpath(path: str, *, start: str | None = None) -> str
def basename(path: str) -> str
def clean_name(name: str, *, replace: str = "_") -> str
def display_name(name: str, *, has_ext: bool = True, title_case: bool = True) -> str
def display_name_from_filepath(name: str) -> str
def display_name_to_filepath(name: str) -> str
def ensure_ext(filepath: str, ext: str, *, case_sensitive: bool = False) -> str
def is_subdir(path: str, directory: str) -> bool
def module_names(path: str, *, recursive: bool = False, package: str = "") -> list[tuple[str, str]]
def native_pathsep(path: str) -> str
def reduce_dirs(dirs: Iterable[str]) -> list[str]
def resolve_ncase(path: str) -> str
def is_autoexec(filepath: str) -> bool     # always False (no auto-run)
extensions_image: frozenset[str]   # lowercase with dot: .png .jpg .jpeg .bmp .tga .tif .tiff .exr .hdr .webp .dds .psd ...
extensions_movie: frozenset[str]   # .mp4 .mov .avi .mkv .webm .ogv .mpg .mpeg ...
extensions_audio: frozenset[str]   # .wav .mp3 .ogg .flac .aac .m4a ...
```

**[O]** rules (judge probe):

- `abspath("//x/y.png")` with no saved file → `"x/y.png"` (the `//` prefix is removed); with a saved
  file (`blend_filepath()` non-empty) or `start` → `os.path.join(base, rest)` with `base =
  start if start is not None else os.path.dirname(blend_filepath())`. A path without `//` is returned unchanged.
- `relpath(p)`: if `p` already starts with `//` → unchanged; empty base → unchanged; otherwise
  `"//" + os.path.relpath(p, base)` with `/` as the separator.
- `basename("//foo/bar.png") == "bar.png"` (removes `//` first).
- `clean_name("my file-1.2 ç!") == "my_file-1_2___"`: keeps only ASCII `[A-Za-z0-9_-]`; every other
  character becomes `replace`.
- `display_name("my_file-name.blend") == "My File-Name"`; `display_name("my_File-NAME") == "my File-NAME"`:
  removes the extension if `has_ext`; `_` → space; if `title_case` and the result is all lowercase, applies
  `str.title()`.
- `display_name_from_filepath("/a/b/my_file.blend") == "my_file"` (base name without extension, no title case).
- `display_name_to_filepath(n)`: replaces each character of `\/:*?"<>|` with `_`.
- `ensure_ext("a.TXT", ".txt") == "a.TXT"`, `ensure_ext("a", ".txt") == "a.txt"`,
  `ensure_ext("a.png", ".txt") == "a.png.txt"` (case-insensitive comparison if `case_sensitive=False`).
- `is_subdir("C:/a/b/c", "C:/a")` is true; `is_subdir("C:/ab", "C:/a")` is false (normalizes and compares by
  components).
- `module_names(path)`: list sorted by name of `(module_name, file_path)` for each `*.py`
  (except `__init__.py`) and each non-hidden folder (does not start with `.`), other than `__pycache__`, that
  contains `__init__.py` (path = the folder `/__init__.py`). With `recursive=True` it includes
  subpackages such as `"pkg.sub"`; `package` prefixes the names (`f"{package}.{name}"`).
- `reduce_dirs`: removes duplicates and directories contained in another one in the list, preserving order.
- `resolve_ncase`: returns the real path with the on-disk casing when it exists; otherwise unchanged.

### 1.2 `quartz.app` (`l1-scaffold-app`)

**L1-app** group: stdlib only. None of these modules imports other Quartz packages.

#### 1.2.1 `quartz/app/__init__.py`

```python
from quartz.app import handlers, timers, msgbus, translations, settings, paths   # submodules
version: tuple[int, int, int] = (0, 1, 0)        # QUARTZ version (Blender's exists only in compat/bpy/app)
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
def trusted() -> bool                 # settings.settings.trust_scripts
def __getattr__(name: str) -> object  # "tempdir" -> str(paths.temp_dir()) + os.sep ; "cachedir" -> str(paths.user_dir()/"cache") + os.sep
```

#### 1.2.2 `quartz/app/handlers.py`

```python
BLENDER_HANDLER_NAMES: tuple[str, ...]   # the 39 names from Appendix A.1, in this order
QUARTZ_HANDLER_NAMES: tuple[str, ...] = ("startup_post", "shutdown_pre", "shutdown_post",
                                          "addon_enable_post", "addon_disable_post")
# one module-level list per name, e.g.: frame_change_pre: list[Callable] = []  (44 lists in total)
def persistent(function: F) -> F                  # function._bpy_persistent = True; returns the same function  [O]
def is_persistent(function: object) -> bool       # getattr(function, "_bpy_persistent", False) is True
def all_lists() -> dict[str, list]                # name -> the list ITSELF (not a copy), in BLENDER + QUARTZ order
def dispatch(name: str, *args: object) -> list[BaseException]
def clear_non_persistent() -> int                 # removes non-persistent functions from ALL lists; returns how many
def snapshot() -> dict[str, list]                 # shallow copies
def restore(snap: dict[str, list]) -> None        # content restored IN PLACE (list identity preserved)
```

- The lists are plain `list`s; the identity of each list never changes (clear with `lst[:] = ...`).
- `dispatch(name, *args)`: `KeyError` if `name` is not one of the 44 names; iterates over a **copy** of the
  list; calls `fn(*args)`; catches `Exception`, prints the traceback to `sys.stderr` and continues;
  returns the captured exceptions.
- Dispatch signatures used by Layer 2 (callbacks must accept `*args`):
  `frame_change_pre/post(scene, depsgraph)`, `depsgraph_update_pre/post(scene, depsgraph)` **[O]**;
  `load_pre/load_post/load_factory_startup_post/save_pre/save_post(filepath: str)` **[I]**;
  `undo_pre/undo_post/redo_pre/redo_post(scene)` **[I]**; `startup_post()`, `shutdown_pre()`,
  `shutdown_post()`; `addon_enable_post(module_name)`, `addon_disable_post(module_name)`.

#### 1.2.3 `quartz/app/timers.py`

```python
def register(function: Callable[[], float | None], *, first_interval: float = 0.0, persistent: bool = False) -> None
def unregister(function: Callable) -> None        # ValueError("Error: function is not registered") if not registered [I]
def is_registered(function: Callable) -> bool
def pump(*, now: float | None = None, max_calls: int = 1000) -> int
def clear(*, keep_persistent: bool = False) -> None
def snapshot() -> list; def restore(snap: list) -> None
```

- Never fires on its own **[O]**. Registering an already registered function again only reschedules it.
- Clock: `time.monotonic()`. Due time = registration instant + `first_interval`.
- `pump(now)`: `now` defaults to `time.monotonic()`; calls, in due-time order (ties: registration
  order), each due timer **at most once per `pump` call**, up to `max_calls`. Return
  `None` → unregisters; `float` → reschedules to `now + value`. Exception in the callback → prints the traceback
  to `stderr` and unregisters. Returns the number of calls made.

#### 1.2.4 `quartz/app/msgbus.py`

```python
def subscribe_rna(*, key: object, owner: object, args: tuple, notify: Callable[..., None],
                  options: set[str] = frozenset()) -> None
def publish_rna(*, key: object) -> None
def clear_by_owner(owner: object) -> None
def notify_changed(struct: object, identifier: str) -> None   # called by Layer 2 when a prop changes
def flush() -> int                                             # delivers the queue; returns number of notify() calls
def pending() -> int
def clear() -> None                                            # removes subscriptions and queue
def snapshot() -> tuple; def restore(snap: tuple) -> None
```

Key matching (for `notify_changed(struct, ident)`): a subscription matches if its `key` is
(a) a tuple `(cls, name)` with `isinstance(struct, cls) and name == ident`; (b) a class `cls` with
`isinstance(struct, cls)`; (c) an object with attributes `_q_struct` and `_q_identifier` (the
`PropertyRef` from §1.6.3) with `key._q_struct is struct and key._q_identifier == ident`; (d) the
`struct` itself (`key is struct`). `publish_rna(key=k)` enqueues the subscriptions whose `key == k` (or `is k`).
Notifications are **deferred** **[O]**: nothing is called before `flush()`. A subscription is called
at most once per `flush()` (`notify(*args)`); exception → traceback to `stderr` and continues.

#### 1.2.5 `quartz/app/translations.py`

```python
locale: str = "en_US"
locales: tuple[str, ...] = ("en_US",)
contexts: TranslationContexts            # immutable namespace with the 60 fields/values of Appendix A.4 [O]
contexts_C_to_py: dict[str, str]         # {f"BLT_I18NCONTEXT_{field.upper()}": field} for each field [I]
class TranslationContexts:               # read-only attributes; __iter__ over the values; unknown -> AttributeError
    ...
def pgettext(msgid: str, msgctxt: str | None = None) -> str
def pgettext_iface(msgid: str, msgctxt: str | None = None) -> str
def pgettext_tip(msgid: str, msgctxt: str | None = None) -> str
def pgettext_rpt(msgid: str, msgctxt: str | None = None) -> str
def pgettext_data(msgid: str, msgctxt: str | None = None) -> str
def pgettext_n(msgid: str, msgctxt: str | None = None) -> str     # always returns msgid
def register(module_name: str, translations_dict: Mapping[str, Mapping[tuple[str | None, str], str]]) -> None
def unregister(module_name: str) -> None                          # silent if absent
def locale_explode(locale: str) -> tuple[str | None, str | None, str | None, str | None, str | None]
def set_locale(name: str) -> None                                 # Quartz only (q_), sets `locale`
```

- `pgettext*`: if `locale` has a translation registered for `(msgctxt or "*", msgid)` (or, with `msgctxt`
  not found, for `("*", msgid)`), it returns it; otherwise it returns `msgid` (in `en_US`, always identity
  **[O]**).
- `locale_explode("pt_BR@euro") == ("pt", "BR", "euro", "pt_BR", "pt@euro")`;
  `locale_explode("pt_BR") == ("pt", "BR", None, "pt_BR", None)`; empty string → five `None` **[I]**.

#### 1.2.6 `quartz/app/settings.py`

```python
@dataclass
class Settings:
    api_prefix: str = "quartz"          # "bpy" with compat active (error messages and repr)
    restrict_register: bool = True      # RestrictBlend during add-on import/register
    lenient_ui: bool = True             # compat synthesizes unknown UI/struct names (and records them)
    record_missing: bool = True         # compat records missing symbols
    strict_layout: bool = False         # UILayout: unknown function -> AttributeError instead of recording
    invoke_in_background: bool = False  # INVOKE_* calls invoke() if True; headless default: execute() [O]
    sweep_mode: bool = False            # blocks network (socket.connect) in the sweep process
    trust_scripts: bool = False
    undo_steps: int = 32
settings: Settings
def reset() -> None                     # restores the defaults ON THE SAME `settings` object
def snapshot() -> dict; def restore(snap: dict) -> None
```

#### 1.2.7 `quartz/app/paths.py`

```python
PROJECT_ROOT: Path                      # Path(__file__).resolve().parents[2]
def user_dir() -> Path                  # Path(os.environ["QUARTZ_USER_DIR"]) if set, otherwise PROJECT_ROOT/"tmp"/"quartz_user"; mkdir(parents=True, exist_ok=True)
def temp_dir() -> Path                  # user_dir()/"temp" (created)
def config_dir() -> Path                # user_dir()/"config" (created)
def scripts_dir() -> Path               # user_dir()/"scripts" (created)
def datafiles_dir() -> Path             # user_dir()/"datafiles" (created)
def extensions_dir() -> Path            # user_dir()/"extensions" (created)
def addon_dirs() -> list[Path]          # the configured list (mutable object); default [scripts_dir()/"addons"]
def extension_repos() -> dict[str, Path]  # default {"user_default": extensions_dir()/"user_default", "system": extensions_dir()/"system"}
def add_addon_dir(path: str | Path) -> None            # no duplicates
def add_extension_repo(module: str, path: str | Path) -> None   # module must be a Python identifier, otherwise ValueError
def compat_dir() -> Path                # Path(os.environ["QUARTZ_COMPAT_DIR"]) if set, otherwise PROJECT_ROOT/"compat"
def reset() -> None                     # forgets configured lists and caches (the env is re-read on the next call)
```

### 1.3 `quartz/errors.py` (`l1-rna-props`)

Normative content (implement exactly these classes; body is free):

```python
class QuartzError(Exception): ...
class RegistrationError(QuartzError, ValueError): ...            # already registered; prop does not register; enum default outside the items
class RegistrationRuntimeError(QuartzError, RuntimeError): ...   # invalid bl_idname; nonexistent parent; unregister without registration; plain class
class MissingClassAttributeError(QuartzError, AttributeError): ...  # missing bl_label / bl_space_type / draw
class ClassValidationError(QuartzError, TypeError): ...          # invalid class enum (bl_space_type, bl_region_type, bl_options)
class PropertyTypeError(QuartzError, TypeError): ...             # wrong type, invalid enum, unknown operator kwarg
class PropertyValueError(QuartzError, ValueError): ...           # wrong sequence size, value rejected by poll
class ReadOnlyError(QuartzError, AttributeError): ...            # read-only prop/context member
class RemovedStructError(QuartzError, ReferenceError): ...       # access to a removed ID
class PollFailedError(QuartzError, RuntimeError): ...
class OperatorFailedError(QuartzError, RuntimeError): ...        # invalid return, exception, report ERROR
class OperatorNotFoundError(QuartzError, AttributeError): ...
class ExecContextError(QuartzError, ValueError): ...             # invalid positionals in operator call
class LinkError(QuartzError, RuntimeError): ...                  # duplicate link / cycle in collections
class RestrictedAccessError(QuartzError, AttributeError): ...    # bpy.data/context during register
class NotImplementedInQuartz(QuartzError, NotImplementedError):
    symbol: str
    def __init__(self, symbol: str, detail: str = "") -> None    # str(exc) == f"{symbol} is not implemented in Quartz" + (f": {detail}" if detail else "")
class ManifestError(QuartzError, ValueError):
    problems: list[str]; path: str
    def __init__(self, problems: Sequence[str], path: str = "") -> None   # str(exc) joins the problems with "; "
class FileFormatError(QuartzError, ValueError): ...              # invalid .qz file
class CompatError(QuartzError, RuntimeError): ...                # conflict when activating compat
```

A test MUST verify `issubclass` of each one with the indicated builtin.

### 1.4 `quartz.math` (= `mathutils`) (`l1-math`)

Group **L1-math**: stdlib + numpy. It does NOT import `quartz.errors` (use builtins: `ValueError`,
`TypeError`, `IndexError`, `ZeroDivisionError`, `NotImplementedError`).

Files: `__init__.py` (re-exports `Vector, Matrix, Quaternion, Euler, Color, axis_conversion` and the
submodules `geometry, kdtree, bvhtree, noise, interpolate, scalar`), `_base.py`, `vector.py`,
`matrix.py`, `quaternion.py`, `euler.py`, `color.py`, `scalar.py`, `conversion.py`, `geometry.py`,
`kdtree.py`, `bvhtree.py`, `noise.py`, `interpolate.py`.

Numeric reference values: `math.*` keys of `data/blender_facts_judge.json` (tolerance
`abs=1e-5`). Tests MUST use them.

#### 1.4.1 Common base (all five classes)

```python
# common attributes/members
is_wrapped: bool            # True if created by _q_wrap
is_frozen: bool
is_valid: bool              # False only if wrapped and getattr(type(owner), "_q_removed", False) is True
owner: object | None        # owner of the wrap (None if not wrapped)
def copy(self) -> Self      # NOT wrapped and NOT frozen copy (Euler preserves order)
def freeze(self) -> Self    # freezes in place and returns self; wrapped -> TypeError("Cannot freeze wrapped data")
def __copy__(self) -> Self; def __deepcopy__(self, memo) -> Self
def __array__(self, dtype=None, copy=None) -> np.ndarray     # copy of the values (float32 unless dtype)
@classmethod
def _q_wrap(cls, view: np.ndarray, *, owner: object = None, on_write: Callable[[], None] | None = None, **extra) -> Self
```

- Storage: internal attribute `_data: np.ndarray` `float32` — shape `(n,)` for Vector/Euler/Color,
  `(4,)` for Quaternion (order `w, x, y, z`), `(rows, columns)` for Matrix (row-major: `m[i]` is
  row `i`). Wrapped: `_data` is the owner's own `view` (same memory, same shape).
- Every in-place mutation (component, slice, `+=`, `normalize()`, `zero()`, setters `x/length/…`) writes
  to `_data` and then calls `on_write()` (if any). Frozen object → `TypeError` on any
  mutation. A wrapped object cannot change size (`resize*` → `TypeError`).
- Reading a component returns `float(self._data[i])`. Computations in `float64`; result stored
  in `float32`.
- `__hash__`: mutable → `TypeError("Vector is not frozen (mutable), call freeze first")` (class name
  in the message) **[O]**; frozen → `hash(tuple(values))`.
- `__eq__`: true only with an instance of the **same class**, same shape and equal `float32` values;
  with `tuple`/`list` → `False` **[O]**. `__ne__` is the complement.

#### 1.4.2 `Vector`

```python
class Vector:
    def __init__(self, seq: Iterable[float] = (0.0, 0.0, 0.0)) -> None      # size >= 2, otherwise ValueError("Vector(): invalid size")
    @classmethod
    def Fill(cls, size: int, fill: float = 0.0) -> Vector
    @classmethod
    def Range(cls, start: int, stop: int | None = None, step: int = 1) -> Vector    # like range(); Range(5) = (0,1,2,3,4)
    @classmethod
    def Linspace(cls, start: float, stop: float, size: int) -> Vector
    @classmethod
    def Repeat(cls, vector: Iterable[float], size: int) -> Vector
    x: float; y: float; z: float; w: float     # rw; component beyond the size -> AttributeError
    # swizzles: any combination of 2–4 letters from "xyzw" limited to the size; read -> new Vector;
    # write allowed only without repeated letters (otherwise AttributeError); requires a sequence of the same length
    length: float              # rw (assigning rescales; a zero vector stays zero)
    length_squared: float
    magnitude: float           # alias of length
    def to_tuple(self, precision: int = -1) -> tuple[float, ...]   # precision >= 0 -> round(v, precision)
    def to_2d(self) -> Vector; def to_3d(self) -> Vector           # pads with 0.0
    def to_4d(self) -> Vector                                      # pads with 0.0 and w = 1.0 if it grows [I]
    def resize(self, size: int) -> None; def resized(self, size: int) -> Vector     # new ones are 0.0
    def resize_2d(self) -> None; def resize_3d(self) -> None; def resize_4d(self) -> None   # resize_4d: w = 1.0 if it grows [I]
    def normalize(self) -> None; def normalized(self) -> Vector    # a zero vector stays zero
    def negate(self) -> None; def zero(self) -> None
    def dot(self, other: Sequence[float]) -> float
    def cross(self, other: Sequence[float]) -> Vector | float      # 3D -> Vector; 2D -> float [O]; other -> ValueError
    def angle(self, other: Sequence[float], fallback: object = None) -> float     # zero: fallback if given, otherwise ValueError
    def angle_signed(self, other: Sequence[float], fallback: object = None) -> float   # 2D only (ValueError otherwise)
    def lerp(self, other: Sequence[float], factor: float) -> Vector
    def slerp(self, other: Sequence[float], factor: float, fallback: object = None) -> Vector
    def project(self, other: Sequence[float]) -> Vector
    def reflect(self, mirror: Sequence[float]) -> Vector
    def orthogonal(self) -> Vector                                 # some perpendicular vector (3D)
    def rotate(self, other: Euler | Quaternion | Matrix) -> None   # 3D, in place
    def rotation_difference(self, other: Sequence[float]) -> Quaternion
    def to_track_quat(self, track: str = "Z", up: str = "Y") -> Quaternion
```

Operators **[O]**: `v + w`, `v - w` (same size, otherwise `ValueError`), `v * s`, `s * v`, `v * w`
(element-wise), `v @ w` (dot product → `float`), `v @ m` (row vector × `Matrix`), `v / s`
(`ZeroDivisionError` on 0), `-v`, `+v`, in place `+=, -=, *=, /=`; `<, <=, >, >=` compare
lengths; `len`, `iter`, `v[i]` (negatives; `IndexError`), `v[a:b]` → `tuple`; assignment by
index and slice.

`repr(Vector((1.0, 2.5, -3.0))) == "Vector((1.0, 2.5, -3.0))"` (each component with `repr(float)`);
`str(...) == "<Vector (1.0000, 2.5000, -3.0000)>"` (4 decimal places) **[O]**.

`to_track_quat(track, up)`: `track ∈ {"X","Y","Z","-X","-Y","-Z"}`, `up ∈ {"X","Y","Z"}`, same axis →
`ValueError`. Returns the rotation that takes the local axis `track` to the direction of the vector, with the local
axis `up` as close as possible to global +Z. Reference **[O]**:
`Vector((0, 1, 0)).to_track_quat("Z", "Y") ≈ (0, 0, 0.707107, 0.707107)` (q and −q are equivalent).

#### 1.4.3 `Matrix`

```python
class Matrix:
    def __init__(self, rows: Iterable[Iterable[float]] | None = None) -> None   # None -> 4x4 identity [O]; 2..4 rows x 2..4 columns, otherwise ValueError
    @classmethod
    def Identity(cls, size: int) -> Matrix
    @classmethod
    def Rotation(cls, angle: float, size: int, axis: str | Sequence[float] | None = None) -> Matrix   # axis "X"|"Y"|"Z"|vector; size 2 ignores axis
    @classmethod
    def Translation(cls, vector: Sequence[float]) -> Matrix        # 4x4
    @classmethod
    def Scale(cls, factor: float, size: int, axis: Sequence[float] | None = None) -> Matrix
    @classmethod
    def Diagonal(cls, vector: Sequence[float]) -> Matrix
    @classmethod
    def OrthoProjection(cls, axis: str | Sequence[float], size: int) -> Matrix   # "X","Y" (2D) | "XY","XZ","YZ" | plane normal
    @classmethod
    def Shear(cls, plane: str, size: int, factor: float | Sequence[float]) -> Matrix   # "X","Y" (2D) | "XY","XZ","YZ"
    @classmethod
    def LocRotScale(cls, location: Sequence[float] | None, rotation: Matrix | Quaternion | Euler | None,
                    scale: Sequence[float] | None) -> Matrix      # 4x4 = T @ R @ S
    row: MatrixAccess          # m.row[i] -> wrapped Vector of the row
    col: MatrixAccess          # m.col[j] -> wrapped Vector of the column (writes go back to the matrix)
    translation: Vector        # rw; 4x4 matrix (column 3, rows 0..2) or 3x3 (column 2, rows 0..1); wrapped
    median_scale: float
    is_identity: bool; is_negative: bool; is_orthogonal: bool; is_orthogonal_axis_vectors: bool
    def determinant(self) -> float                     # non-square -> ValueError
    def transpose(self) -> None; def transposed(self) -> Matrix
    def invert(self, fallback: Matrix | None = None) -> None     # singular without fallback -> ValueError("Matrix.invert(ed): matrix does not have an inverse"); with fallback: copies fallback
    def inverted(self, fallback: object = ...) -> Matrix | object  # singular: returns fallback if given, otherwise ValueError
    def invert_safe(self) -> None; def inverted_safe(self) -> Matrix   # singular -> pseudo-inverse
    def adjugate(self) -> None; def adjugated(self) -> Matrix
    def normalize(self) -> None; def normalized(self) -> Matrix   # normalizes the columns of the 3x3 part
    def zero(self) -> None; def identity(self) -> None
    def to_2x2(self) -> Matrix; def to_3x3(self) -> Matrix; def to_4x4(self) -> Matrix; def resize_4x4(self) -> None
    def to_euler(self, order: str = "XYZ", euler_compat: Euler | None = None) -> Euler
    def to_quaternion(self) -> Quaternion
    def to_scale(self) -> Vector; def to_translation(self) -> Vector
    def decompose(self) -> tuple[Vector, Quaternion, Vector]          # (loc, rot, scale) [O]
    def lerp(self, other: Matrix, factor: float) -> Matrix
    def rotate(self, other: Euler | Quaternion | Matrix) -> None
```

Operators: `m @ n` (columns of `m` == rows of `n`, otherwise `ValueError`); `m @ v` (len == columns;
**4×4 @ Vector of 3** uses `w = 1` and returns 3 components without perspective division — `Translation((1,2,3))
@ (1,1,1) == (2,3,4)` **[O]**); `v @ m` row vector **[O]**; `m * n` element-wise; `m * s`,
`s * m`, `m + n`, `m - n`, `-m`; `m[i]` → wrapped row; `m[i] = seq`; `len(m)` = rows; `iter` by
rows.

`Matrix.Rotation(math.pi/2, 3, "Z") == ((0,-1,0),(1,0,0),(0,0,1))` **[O]**.

`repr(Matrix.Identity(3)) == "Matrix(((1.0, 0.0, 0.0),\n        (0.0, 1.0, 0.0),\n        (0.0, 0.0, 1.0)))"`
**[O]** (first row after `"Matrix(("`, the others with 8 spaces, separator `",\n"`, closes with `"))"`).

#### 1.4.4 `Quaternion`

```python
class Quaternion:
    def __init__(self, seq: Sequence[float] = (1.0, 0.0, 0.0, 0.0), angle: float | None = None) -> None
        # angle given: seq is the AXIS (3) -> axis-angle; seq of 3 without angle -> exponential map; seq of 4 -> (w, x, y, z)
    w: float; x: float; y: float; z: float      # rw
    angle: float                                # rw (keeps the axis)
    axis: Vector                                # rw (keeps the angle); returns a copy
    magnitude: float
    def conjugate(self) -> None; def conjugated(self) -> Quaternion
    def invert(self) -> None; def inverted(self) -> Quaternion
    def normalize(self) -> None; def normalized(self) -> Quaternion
    def negate(self) -> None; def identity(self) -> None
    def dot(self, other: Quaternion) -> float
    def cross(self, other: Quaternion) -> Quaternion            # = Hamilton product self @ other
    def rotation_difference(self, other: Quaternion) -> Quaternion   # q such that q @ self == other [I]
    def slerp(self, other: Quaternion, factor: float) -> Quaternion
    def rotate(self, other: Euler | Quaternion | Matrix) -> None
    def make_compatible(self, other: Quaternion) -> None        # flips the sign if dot(self, other) < 0
    def to_matrix(self) -> Matrix                                # 3x3
    def to_euler(self, order: str = "XYZ", euler_compat: Euler | None = None) -> Euler
    def to_axis_angle(self) -> tuple[Vector, float]
    def to_exponential_map(self) -> Vector
    def to_swing_twist(self, axis: str) -> tuple[Quaternion, float]
```

Operators: `q @ p` composition (Hamilton); `q @ v` rotates a `Vector` of 3; `q * p` and `q * s` element-wise;
`q + p`, `q - p`, `-q`; indexing 0..3 = `w, x, y, z`. References **[O]**:
`Quaternion((0, 0, 1), math.pi/2) ≈ (0.707107, 0, 0, 0.707107)`;
`Euler((0.1, 0.2, 0.3), "XYZ").to_quaternion() ≈ (0.983347, 0.034271, 0.106021, 0.143572)`;
`repr(Quaternion()) == "Quaternion((1.0, 0.0, 0.0, 0.0))"`.

#### 1.4.5 `Euler`

```python
EULER_ORDERS: tuple[str, ...] = ("XYZ", "XZY", "YXZ", "YZX", "ZXY", "ZYX")
class Euler:
    def __init__(self, angles: Sequence[float] = (0.0, 0.0, 0.0), order: str = "XYZ") -> None   # invalid order -> ValueError
    x: float; y: float; z: float; order: str     # rw
    def to_matrix(self) -> Matrix                # 3x3
    def to_quaternion(self) -> Quaternion
    def rotate(self, other: Euler | Quaternion | Matrix) -> None
    def rotate_axis(self, axis: str, angle: float) -> None      # extra rotation around the given LOCAL axis [I]
    def make_compatible(self, other: Euler) -> None             # adjusts ±2π to stay close to other
    def zero(self) -> None
    @classmethod
    def _q_wrap(cls, view, *, owner=None, on_write=None, order: str = "XYZ") -> Euler
```

Convention **[O]**: the order string is the order of **application**; the matrix is `R(last) @ R(middle) @
R(first)`. `"XYZ"` → `Rz @ Ry @ Rx`; `"ZYX"` → `Rx @ Ry @ Rz` (values in
`math.euler_xyz`/`math.euler_zyx`). Only `==`, indexing and `len` (3) as operators.
`repr(Euler((0.1, 0.2, 0.3))) == "Euler((0.10000000149011612, 0.20000000298023224, 0.30000001192092896), 'XYZ')"` **[O]**.

#### 1.4.6 `Color`

```python
class Color:
    def __init__(self, rgb: Sequence[float] = (0.0, 0.0, 0.0)) -> None   # exactly 3
    r: float; g: float; b: float; h: float; s: float; v: float          # rw
    hsv: tuple[float, float, float]                                      # rw
    def from_scene_linear_to_srgb(self) -> Color
    def from_srgb_to_scene_linear(self) -> Color
    # from_aces_to_scene_linear, from_scene_linear_to_aces, from_rec709_linear_to_scene_linear, from_scene_linear_to_rec709_linear,
    # from_rec2020_linear_to_scene_linear, from_scene_linear_to_rec2020_linear, from_xyz_d65_to_scene_linear, from_scene_linear_to_xyz_d65
    #   -> NotImplementedError("Color.<name> is not implemented in Quartz")
```

Operators: `c + d`, `c - d`, `c * s`, `s * c`, `==`, indexing. `Color((1.0, 0.5, 0.0)).hsv ≈
(0.083333, 1.0, 1.0)` **[O]**; `repr` = `"Color((1.0, 0.5, 0.0))"`.

#### 1.4.7 `conversion.py`, `scalar.py`

```python
def axis_conversion(from_forward: str = "Y", from_up: str = "Z", to_forward: str = "Y", to_up: str = "Z") -> Matrix
    # 3x3 that takes the "from" basis to the "to" basis; axes in {"X","Y","Z","-X","-Y","-Z"};
    # forward and up on the same axis -> ValueError("Invalid axis arguments passed, can't use up/forward on the same axis")
def clamp(value: float, min: float = 0.0, max: float = 1.0) -> float
def lerp(from_value: float, to_value: float, factor: float) -> float
def smoothstep(from_value: float, to_value: float, value: float) -> float   # Hermite 3t²-2t³ with t clamped to [0,1]
```

#### 1.4.8 `geometry.py` (= `mathutils.geometry`, subset)

```python
def intersect_ray_tri(v1, v2, v3, ray, orig, clip: bool = True) -> Vector | None
def intersect_line_line(v1, v2, v3, v4) -> tuple[Vector, Vector] | None          # closest points; parallel -> None
def intersect_line_plane(line_a, line_b, plane_co, plane_no, no_flip: bool = False) -> Vector | None
def intersect_line_sphere(line_a, line_b, sphere_co, sphere_radius: float, clip: bool = True) -> tuple[Vector | None, Vector | None]
def intersect_point_line(pt, line_p1, line_p2) -> tuple[Vector, float]           # (closest point, factor t)
def intersect_point_tri(pt, tri_p1, tri_p2, tri_p3) -> Vector | None             # projection inside the triangle, otherwise None
def intersect_point_tri_2d(pt, tri_p1, tri_p2, tri_p3) -> int                    # 1 inside, 0 outside
def closest_point_on_tri(pt, tri_p1, tri_p2, tri_p3) -> Vector
def distance_point_to_plane(pt, plane_co, plane_no) -> float                     # signed
def normal(*vectors) -> Vector                                                   # Newell; also accepts a single sequence of vectors
def area_tri(v1, v2, v3) -> float                                                # 2D or 3D
def volume_tetrahedron(v1, v2, v3, v4) -> float
def barycentric_transform(point, tri_a1, tri_a2, tri_a3, tri_b1, tri_b2, tri_b3) -> Vector
def tessellate_polygon(veclist_list) -> list[tuple[int, int, int]]               # indices into the concatenation of the polylines
def interpolate_bezier(knot1, handle1, handle2, knot2, resolution: int) -> list[Vector]   # `resolution` points including endpoints
def convex_hull_2d(points) -> list[int]                                          # counterclockwise
def box_fit_2d(points) -> float                                                  # angle of the smallest box
def box_pack_2d(boxes: list[list[float]]) -> tuple[float, float]                 # boxes [x, y, w, h] modified in place
def delaunay_2d_cdt(*args, **kwargs) -> NoReturn                                 # NotImplementedError
```

Inputs accept `Vector`, tuples, lists or arrays.

#### 1.4.9 `kdtree.py`, `bvhtree.py`, `noise.py`, `interpolate.py`

```python
class KDTree:
    def __init__(self, size: int) -> None
    def insert(self, co: Sequence[float], index: int) -> None       # beyond `size` -> ValueError [I]; unbalances
    def balance(self) -> None
    def find(self, co, filter: Callable[[int], bool] | None = None) -> tuple[Vector | None, int | None, float | None]
    def find_n(self, co, n: int) -> list[tuple[Vector, int, float]]          # sorted by distance
    def find_range(self, co, radius: float) -> list[tuple[Vector, int, float]]   # dist <= radius, sorted
    # query before balance() -> RuntimeError("KDTree must be balanced before use") [I]; tie: lowest index
class BVHTree:
    @classmethod
    def FromPolygons(cls, vertices, polygons, all_triangles: bool = False, epsilon: float = 0.0) -> BVHTree
    @classmethod
    def FromBMesh(cls, bmesh, epsilon: float = 0.0) -> BVHTree                # uses the installed adapter
    @classmethod
    def FromObject(cls, object, depsgraph, *, deform: bool = True, render: bool = False, cage: bool = False, epsilon: float = 0.0) -> BVHTree
    @classmethod
    def _q_from_triangles(cls, positions: np.ndarray, tris: np.ndarray, tri_polygon: np.ndarray, epsilon: float = 0.0) -> BVHTree
    def ray_cast(self, origin, direction, distance: float = sys.float_info.max) -> tuple[Vector | None, Vector | None, int | None, float | None]
    def find_nearest(self, origin, distance: float = sys.float_info.max) -> tuple[Vector | None, Vector | None, int | None, float | None]
    def find_nearest_range(self, origin, distance: float = sys.float_info.max) -> list[tuple[Vector, Vector, int, float]]
    def overlap(self, other_tree: BVHTree) -> list[tuple[int, int]]
def set_object_adapter(fn: Callable[..., BVHTree] | None) -> None     # installed by quartz.extras (L3)
def set_bmesh_adapter(fn: Callable[..., BVHTree] | None) -> None      # installed by quartz.bmesh (L3)
# no adapter: FromObject/FromBMesh -> NotImplementedError("BVHTree.FromObject is not available (adapter not installed)")
```

The returned `index` is the index of the input polygon; a miss tuple = four `None`. Brute force in numpy
is acceptable.

`noise.py`: `random() -> float` in [0,1), `seed_set(seed: int) -> None`, `random_unit_vector(size: int =
3) -> Vector`, `random_vector(size: int = 3) -> Vector` (components in [−1,1)) — own values;
all the other `mathutils.noise` names (`noise, noise_vector, turbulence, turbulence_vector,
fractal, multi_fractal, hetero_terrain, hybrid_multi_fractal, ridged_multi_fractal,
variable_lacunarity, voronoi, cell, cell_vector`) exist and raise
`NotImplementedError("mathutils.noise.<name> is not implemented in Quartz")`.
`interpolate.py`: `poly_3d_calc(veclist, pt) -> list[float]` (weights that sum to 1; triangle =
barycentric).

### 1.5 `quartz.geometry` (`l1-geometry`)

Group **L1-geometry**: stdlib + numpy; it knows neither ID nor `quartz.math` (rotation conventions
duplicated in `transform.py`, tested against the same references).

Files: `__init__.py` (re-exports everything below), `attributes.py`, `mesh.py`, `topology.py`,
`normals.py`, `triangulate.py`, `primitives.py`, `transform.py`.

#### 1.5.1 `attributes.py`

```python
DOMAINS: tuple[str, ...] = ("POINT", "EDGE", "FACE", "CORNER")
DATA_TYPES: Mapping[str, tuple[np.dtype, tuple[int, ...]]]
#  "FLOAT": (float32, ()), "INT": (int32, ()), "INT8": (int8, ()), "BOOLEAN": (bool_, ()),
#  "FLOAT_VECTOR": (float32, (3,)), "FLOAT2": (float32, (2,)), "INT16_2D": (int16, (2,)), "INT32_2D": (int32, (2,)),
#  "FLOAT_COLOR": (float32, (4,)), "BYTE_COLOR": (uint8, (4,)), "QUATERNION": (float32, (4,)), "FLOAT4X4": (float32, (4, 4))
REQUIRED_ATTRIBUTES: frozenset[str] = frozenset({"position", ".edge_verts", ".corner_vert", ".corner_edge"})
def default_fill(data_type: str) -> object       # zeros; QUATERNION (1,0,0,0); FLOAT4X4 identity
@dataclass
class AttributeArray:
    name: str; domain: str; data_type: str; data: np.ndarray       # shape (n, *shape)
    @property
    def is_internal(self) -> bool       # name.startswith(".")
    @property
    def is_required(self) -> bool
    def copy(self) -> AttributeArray
class AttributeStore:
    def __init__(self, sizes: Callable[[str], int]) -> None
    def new(self, name: str, data_type: str, domain: str, *, fill: object = None) -> AttributeArray
        # existing name -> ValueError; invalid type/domain -> ValueError
    def get(self, name: str) -> AttributeArray | None
    def __getitem__(self, name: str) -> AttributeArray     # KeyError
    def __contains__(self, name: str) -> bool; def __iter__(self) -> Iterator[AttributeArray]; def __len__(self) -> int
    def remove(self, name: str) -> None                    # KeyError if absent; ValueError if required
    def rename(self, old: str, new: str) -> None           # ValueError if `new` exists
    def names(self, domain: str | None = None, *, include_internal: bool = True) -> list[str]
    def by_domain(self, domain: str) -> list[AttributeArray]
    def resize(self, domain: str, size: int) -> None       # truncates or extends ALL arrays of the domain (default_fill)
    def unique_name(self, base: str) -> str                # base, base.001, base.002, …
    def copy(self, sizes: Callable[[str], int]) -> AttributeStore
```

Iteration is in insertion order.

#### 1.5.2 `mesh.py`

```python
class MeshGeometry:
    attributes: AttributeStore
    face_offsets: np.ndarray            # (F+1,) int32; [0] == 0; non-decreasing; [-1] == num_corners
    def __init__(self) -> None          # empty: required attributes with 0 rows; face_offsets == [0]
    @classmethod
    def empty(cls) -> MeshGeometry
    @classmethod
    def from_pydata(cls, vertices, edges=(), faces=(), *, shade_flat: bool = True) -> MeshGeometry
    positions: np.ndarray               # live view (V,3) float32 of "position"
    edges: np.ndarray                   # live view (E,2) int32 of ".edge_verts"
    corner_verts: np.ndarray            # live view (L,) int32 of ".corner_vert"
    corner_edges: np.ndarray            # live view (L,) int32 of ".corner_edge"
    num_verts: int; num_edges: int; num_faces: int; num_corners: int
    def domain_size(self, domain: str) -> int
    def face_sizes(self) -> np.ndarray          # (F,) int32
    def corner_to_face(self) -> np.ndarray      # (L,) int32
    def resize_domain(self, domain: str, size: int) -> None
    def add_verts(self, count: int) -> slice
    def add_edges(self, count: int) -> slice
    def add_corners(self, count: int) -> slice
    def add_faces(self, sizes: Sequence[int] | int) -> slice
        # int: `count` empty faces at the end (offsets repeat the last one); sequence: faces with those sizes AND the corresponding corners
    def set_face_offsets(self, loop_starts: ArrayLike) -> None   # offsets[:-1] = loop_starts; offsets[-1] = num_corners; decreasing -> ValueError
    def copy(self) -> MeshGeometry              # deep
    def clear(self) -> None                     # all domains to 0
    def validate(self, *, fix: bool = False) -> tuple[bool, list[str]]   # (changed?, problems)
```

`from_pydata` **[O]**: `float32` positions; faces with ≥ 3 valid indices (otherwise `ValueError`); explicit
edges first (no duplicates), then the edges of the faces in order of first occurrence
(corner `i` → `(v_i, v_{i+1})`, unoriented key); computes `.corner_edge`; creates `.select_vert`,
`.select_edge`, `.select_poly` (false) and `sharp_face` (= `shade_flat`). A quad → 4 v / 4 e / 4 corners /
1 face. `validate()` on a correct mesh → `(False, [])`. Problems detected: index out of range,
degenerate or duplicate edge, face with < 3 corners, inconsistent `.corner_edge`, invalid offsets,
non-finite positions; `fix=True` removes what is invalid and recomputes `.corner_edge`.

#### 1.5.3 `topology.py`, `normals.py`, `triangulate.py`

```python
def calc_edges(geo: MeshGeometry, *, keep_existing: bool = True) -> None     # rebuilds .edge_verts from the faces (+ existing ones) and .corner_edge
def edge_keys(edges: np.ndarray) -> np.ndarray                                # (E,2) each row sorted
def face_edge_keys(geo: MeshGeometry, face_index: int) -> list[tuple[int, int]]
    # pairs (v_i, v_{i+1}) of each corner, each pair sorted, in corner order: quad 0123 -> [(0,1),(1,2),(2,3),(0,3)] [O]
def loose_edges(geo: MeshGeometry) -> np.ndarray      # (E,) bool
def loose_verts(geo: MeshGeometry) -> np.ndarray      # (V,) bool
def faces_to_offsets(faces: Sequence[Sequence[int]]) -> tuple[np.ndarray, np.ndarray]   # (face_offsets, corner_verts)
def flip_faces(geo: MeshGeometry, mask: np.ndarray | None = None) -> None   # reverses the winding keeping the 1st corner [I]
def join(geos: Sequence[MeshGeometry], matrices: Sequence[np.ndarray] | None = None) -> MeshGeometry
def merge_by_distance(geo: MeshGeometry, distance: float) -> np.ndarray      # old index -> new index map (does not modify geo)

def face_normals(geo) -> np.ndarray      # (F,3) float32, normalized Newell; degenerate -> (0,0,0)
def vertex_normals(geo) -> np.ndarray    # (V,3) angle-weighted average, normalized; loose vertex -> normalized position [I]
def corner_normals(geo, *, sharp_face: np.ndarray | None = None) -> np.ndarray   # (L,3): flat face -> face normal; otherwise vertex normal
def face_centers(geo) -> np.ndarray      # (F,3) mean of the corners
def face_areas(geo) -> np.ndarray        # (F,)

def triangulate(geo) -> tuple[np.ndarray, np.ndarray]   # (tris (T,3) CORNER indices, tri_face (T,)); quad along the shortest diagonal; n-gon by ear clipping in the face plane
def triangulated(geo) -> MeshGeometry                    # new geometry of triangles only (copies attributes per domain)
```

#### 1.5.4 `primitives.py`

All return a `MeshGeometry` centered at the origin, Z up, faces pointing outward, `sharp_face` true
(flat shading **[O]**) and, if `calc_uvs`, a `"UVMap"` attribute (`CORNER`, `FLOAT2`) with its
own UVs in [0,1]. Counts **[O]** with the defaults (boxes for the default parameters):

| Function (defaults) | v / e / f / corners | bounding box |
|---|---|---|
| `plane(size=2.0, *, calc_uvs=True)` | 4 / 4 / 1 / 4 | (−1,−1,0)…(1,1,0) |
| `cube(size=2.0, *, calc_uvs=True)` | 8 / 12 / 6 / 24 | ±1 |
| `circle(vertices=32, radius=1.0, fill_type="NOTHING", *, calc_uvs=True)` | 32 / 32 / 0 / 0 (`NGON`: f 1, corners 32; `TRIFAN`: v 33, e 64, f 32, corners 96) | (−1,−1,0)…(1,1,0) |
| `uv_sphere(segments=32, ring_count=16, radius=1.0, *, calc_uvs=True)` | 482 / 992 / 512 / 1984 | ±1 (poles at ±Z) |
| `ico_sphere(subdivisions=2, radius=1.0, *, calc_uvs=True)` | 42 / 120 / 80 / 240 (`subdivisions=1`: 12 / 30 / 20 / 60) | inside the sphere of radius 1 |
| `cylinder(vertices=32, radius=1.0, depth=2.0, end_fill_type="NGON", *, calc_uvs=True)` | 64 / 96 / 34 / 192 (`NOTHING`: f 32, corners 128; `TRIFAN`: v 66, e 160, f 96, corners 320) | ±1 |
| `cone(vertices=32, radius1=1.0, radius2=0.0, depth=2.0, end_fill_type="NGON", *, calc_uvs=True)` | 33 / 64 / 33 / 128 (`radius2 > 0`: like cylinder, 64 v) | ±1 |
| `grid(x_subdivisions=10, y_subdivisions=10, size=2.0, *, calc_uvs=True)` | 121 / 220 / 100 / 400 ((x+1)(y+1) vertices, x·y faces) | (−1,−1,0)…(1,1,0) |
| `torus(major_segments=48, minor_segments=12, major_radius=1.0, minor_radius=0.25, *, calc_uvs=True)` | 576 / 1152 / 576 / 2304 | (−1,25,−1,25,−0,25)…(1,25,1,25,0,25) |

Parameters outside the limits of the corresponding operator in the dump are clamped by the **operator**, not
here; here invalid values (e.g. `vertices < 3`) raise `ValueError`. The vertex order is
own (clean-room); only counts, boxes and topological invariants are contract.

#### 1.5.5 `transform.py`

```python
def euler_to_matrix3(angles: ArrayLike, order: str = "XYZ") -> np.ndarray   # (3,3) float64; same convention as §1.4.5
def quat_to_matrix3(q: ArrayLike) -> np.ndarray                             # q = (w, x, y, z)
def matrix3_to_quat(m: ArrayLike) -> np.ndarray
def compose_trs(location: ArrayLike, rotation3: ArrayLike, scale: ArrayLike) -> np.ndarray   # (4,4) float64 = T @ R @ S
def decompose_trs(m4: ArrayLike) -> tuple[np.ndarray, np.ndarray, np.ndarray]   # (loc(3), quat wxyz(4), scale(3)); det<0 -> negates the 3 scales [I]
def transform_points(points: np.ndarray, m4: ArrayLike) -> np.ndarray       # (N,3); returns the input dtype
def transform_directions(dirs: np.ndarray, m4: ArrayLike, *, normalize: bool = False) -> np.ndarray
def transform_normals(normals: np.ndarray, m4: ArrayLike) -> np.ndarray     # inverse-transpose of the 3x3, normalized
def bounds(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]             # (min, max); empty -> zeros
def bound_box(points: np.ndarray) -> np.ndarray
    # (8,3) corners in the order 0(-,-,-) 1(-,-,+) 2(-,+,+) 3(-,+,-) 4(+,-,-) 5(+,-,+) 6(+,+,+) 7(+,+,-) [I]
```

### 1.6 `quartz.props` and `quartz.rna` (`l1-rna-props`)

Group **L1-rna**: stdlib + numpy + the group itself (`quartz.errors`, `quartz.props`, `quartz.rna.*`).
It does not import `quartz.math` or `quartz.app` (use `quartz.rna.hooks`).

Files: `quartz/props.py`, `quartz/rna/__init__.py`, `hooks.py`, `datapath.py`, `properties.py`,
`collections.py`, `annotations.py`, `struct.py`, `idprops.py`, `rnainfo.py`, `description.py`.

`quartz/rna/__init__.py` re-exports: `Struct, StructMeta, PropertyGroup, builtin_struct, IDRef,
PropertyDef, BoolDef, IntDef, FloatDef, StringDef, EnumDef, PointerDef, CollectionDef, EnumItem,
PropCollection, GroupCollection, PropArray, IDPropertyGroup, IDPropertyArray, IDPropertyUIManager,
rna_idprop_ui_create, rna_idprop_value_to_python, rna_idprop_quote_path, RNAStruct, RNAProperty,
RNAEnumItem, Description, describe, collect_annotations, install_properties, uninstall_properties,
define_property, remove_property, get_property, iter_properties, PropertyRef, hooks, datapath`.

#### 1.6.1 `quartz/props.py` (= `bpy.props`)

```python
class _PropertyDeferred:
    __slots__ = ("function", "keywords", "_kind")
    function: Callable[..., "_PropertyDeferred"]   # the public factory that created it [O]
    keywords: dict[str, object]                    # ONLY the arguments passed (positional becomes a name) [O]
    _kind: str     # "BOOLEAN" | "BOOLEAN_VECTOR" | "INT" | "INT_VECTOR" | "FLOAT" | "FLOAT_VECTOR" | "STRING" | "ENUM" | "POINTER" | "COLLECTION"
    def __init__(self, function: Callable, keywords: dict[str, object], kind: str) -> None
    def __repr__(self) -> str      # f"<_PropertyDeferred, {function.__name__}, {keywords!r}>"

FACTORY_NAMES: Mapping[str, str]        # kind -> "BoolProperty", "BoolVectorProperty", "IntProperty", ...
PROPERTY_KWARGS: Mapping[str, tuple[str, ...]]   # factory name -> kwargs from 5.2.2 (Appendix A.5), in dump order
NATIVE_KWARGS: frozenset[str] = frozenset({"meta"})
POSITIONAL_PARAM: Mapping[str, str] = {"EnumProperty": "items", "PointerProperty": "type", "CollectionProperty": "type"}

def make_deferred(function: Callable, kind: str, args: tuple, kwargs: dict, *, allow_meta: bool = True) -> _PropertyDeferred
    # kwargs outside PROPERTY_KWARGS[...] (+ "meta" if allow_meta) -> TypeError(f"{factory}() got an unexpected keyword argument '{k}'")
    # positional: only 1, and only for the POSITIONAL_PARAM factories; otherwise TypeError(f"{factory}() takes 0 positional arguments")
    # positional and named at the same time -> TypeError
def BoolProperty(*args, **kwargs) -> _PropertyDeferred          # = make_deferred(BoolProperty, "BOOLEAN", args, kwargs)
def BoolVectorProperty(*args, **kwargs) -> _PropertyDeferred
def IntProperty(*args, **kwargs) -> _PropertyDeferred
def IntVectorProperty(*args, **kwargs) -> _PropertyDeferred
def FloatProperty(*args, **kwargs) -> _PropertyDeferred
def FloatVectorProperty(*args, **kwargs) -> _PropertyDeferred
def StringProperty(*args, **kwargs) -> _PropertyDeferred
def EnumProperty(*args, **kwargs) -> _PropertyDeferred          # items required (positional or named) -> otherwise TypeError
def PointerProperty(*args, **kwargs) -> _PropertyDeferred       # type required
def CollectionProperty(*args, **kwargs) -> _PropertyDeferred    # type required
def RemoveProperty(cls: type, *, attr: str) -> None             # = quartz.rna.remove_property(cls, attr)
```

`IntProperty(name="x", default=3)` → `function is IntProperty`, `keywords == {"name": "x", "default": 3}`
**[O]**. The factories do NOT validate values (that happens when the `PropertyDef` is built, §1.6.4). Defaults
(Appendix A.5) **[O]**: Float `default=0.0`, `min/max/soft_min/soft_max=∓3.402823e+38`, `step=3`,
`precision=2`; Int `min/soft_min=-2**31`, `max/soft_max=2**31-1`, `step=1`; vectors `size=3`;
`options={'ANIMATABLE'}`; `subtype='NONE'`; `unit='NONE'`; String `maxlen=0`,
`search_options={'SUGGESTION'}`; Enum `default=None`.

**Native kwarg `meta`** (only on the `quartz` face; the compat `bpy.props` rejects it): `Mapping[str, object]`
with these keys (all optional; unknown key → `RegistrationError` at construction):

| Key | Type | Meaning |
|---|---|---|
| `group` | `str` | UI group/tab (C4D description) |
| `parent` | `str` | prop on which this one visually depends (C4D PARENTID) |
| `enabled_if` | `Callable[[inst], bool]` | conditional enabling |
| `visible_if` | `Callable[[inst], bool]` | conditional visibility |
| `widget` | `str` | widget hint (`"SLIDER"`, `"COLOR"`, `"FILE"`, …) |
| `dirty` | `str` | dirty channel bumped on write (default `"DATA"`; see §2.2.3) |
| `uid` | `int` | optional stable numeric ID (never the primary key) |
| `since` | `int` | schema version that introduced the prop |
| `on_remove` | `"CLEAR"` \| `"DELETE_OWNER"` | pointer to ID: what to do when the target is removed (default `"CLEAR"`) |
| `counts_user` | `bool` | pointer to ID counts as a user (default `True`) |
| `virtual_get` | `Callable[[inst], object]` | computed prop: returns the **final** value (for arrays, an `np.ndarray`, preferably a live view) |
| `virtual_set` | `Callable[[inst, object], None]` \| `None` | receives the **already coerced** value (enum: identifier; flag: `set`; array: `np.ndarray`); absent → read-only |
| `euler_order` | `Callable[[inst], str]` | order of the `Euler` returned for subtype `EULER` |
| `fixed_type_name` | `str` | RNA name of the pointed-to type when `type=` is a generic base (only for `to_rna_dict`) |
| `readonly` | `bool` | forces read-only |
| `doc` | `str` | additional documentation |

#### 1.6.2 `quartz/rna/hooks.py`

```python
HOOK_NAMES: tuple[str, ...] = ("wrap_array", "current_context", "on_property_changed",
                               "on_type_property_defined", "on_type_property_removed", "note_missing", "repr_root")
def wrap_array(values: np.ndarray, pdef: "PropertyDef", inst: object, on_write: Callable[[], None]) -> object
    # default: PropArray(values, on_write=on_write, owner=inst, pdef=pdef)
def current_context() -> object | None                   # default: None
def on_property_changed(inst: object, pdef: "PropertyDef") -> None    # default: no-op
def on_type_property_defined(cls: type, identifier: str) -> None      # default: no-op
def on_type_property_removed(cls: type, identifier: str) -> None      # default: no-op
def note_missing(symbol: str) -> None                    # default: no-op
def repr_root() -> str                                   # default: "quartz"
def install(**implementations: Callable | None) -> None  # replaces only the named hooks; None restores the default; unknown name -> TypeError
def reset() -> None                                      # all back to defaults
def snapshot() -> dict[str, Callable]; def restore(snap: dict[str, Callable]) -> None
```

Who installs (one owner per hook): `quartz.types` (L2) → `wrap_array`, `on_property_changed`;
`quartz.registry` (L2) → `on_type_property_defined/removed`; `quartz.session` (L2) →
`current_context`; `quartz.compat` (L3) → `note_missing`, `repr_root`.

#### 1.6.3 `quartz/rna/datapath.py`

```python
@dataclass(frozen=True)
class PathToken:
    kind: Literal["ATTR", "INDEX", "KEY"]
    value: str | int
def parse(path: str) -> tuple[PathToken, ...]
    # 'modifiers["Bend"].angle[0]' -> ATTR modifiers, KEY "Bend", ATTR angle, INDEX 0; key between "..." or '...' with \" and \\ ;
    # "" -> (); syntax error -> ValueError(f'invalid data path "{path}"')
def format(tokens: Iterable[PathToken]) -> str        # ATTR by ".", INDEX "[n]", KEY '["escaped"]'
def resolve(root: object, path: str, *, coerce: bool = True) -> object
    # ATTR -> getattr; INDEX/KEY -> root[value]; failure -> ValueError(f'Path "{path}" could not be resolved')
    # coerce=False and the last token is an ATTR of a PropertyDef of a Struct -> PropertyRef(struct, identifier, None);
    #   ATTR + final INDEX on an array -> PropertyRef(struct, identifier, index)
def escape_identifier(string: str) -> str             # '\\' -> '\\\\' and '"' -> '\\"' [O]
def unescape_identifier(string: str) -> str
class PropertyRef:
    __slots__ = ("_q_struct", "_q_identifier", "_q_index")
    def __init__(self, struct: object, identifier: str, index: int | None = None) -> None
    struct: object; identifier: str; index: int | None     # read-only properties
    # __eq__: same struct (is), identifier and index; __hash__ consistent; used as the msgbus key
```

#### 1.6.4 `quartz/rna/properties.py`

```python
FLOAT_MAX: float = 3.4028234663852886e38
INT_MIN: int = -2**31; INT_MAX: int = 2**31 - 1
OPTION_FLAGS: frozenset[str]          # HIDDEN SKIP_SAVE SKIP_PRESET ANIMATABLE LIBRARY_EDITABLE PROPORTIONAL TEXTEDIT_UPDATE
                                      # OUTPUT_PATH PATH_SUPPORTS_BLEND_RELATIVE PATH_SUPPORTS_TEMPLATES ENUM_FLAG
OVERRIDE_FLAGS: frozenset[str]        # LIBRARY_OVERRIDABLE NO_PROPERTY_NAME
META_KEYS: frozenset[str]             # table in §1.6.1
def to_float32(value: float) -> float                      # float(np.float32(value))
@dataclass(frozen=True)
class EnumItem:
    identifier: str; name: str; description: str; icon: str | int; value: int
def normalize_enum_items(items: Iterable, *, is_flag: bool = False) -> tuple[EnumItem, ...]
    # accepts (id, name, desc), (id, name, desc, icon), (id, name, desc, icon, number), (id, name, desc, number:int);
    # None = separator (ignored); default value = index (flags: 1 << index); duplicate identifier -> ValueError

class PropertyDef:
    kind: ClassVar[str]          # "BOOLEAN" | "INT" | "FLOAT" | "STRING" | "ENUM" | "POINTER" | "COLLECTION"
    identifier: str
    owner: type | None
    deferred: "_PropertyDeferred | None"
    name: str; description: str; translation_context: str
    options: frozenset[str]; override: frozenset[str]; tags: frozenset[str]
    subtype: str; unit: str
    update: Callable | None; get: Callable | None; set: Callable | None
    get_transform: Callable | None; set_transform: Callable | None
    meta: Mapping[str, object]   # MappingProxyType (empty if not given)
    size: tuple[int, ...]        # () scalar; (n,) vector; (rows, columns) 2D
    is_array: bool; array_length: int          # product of size (0 if scalar)
    is_readonly: bool            # (get and not set) or (virtual_get and not virtual_set) or meta["readonly"]
    is_hidden: bool; is_skip_save: bool; is_animatable: bool; is_enum_flag: bool; is_never_none: bool
    def __get__(self, inst: object | None, owner_cls: type | None = None) -> object
    def __set__(self, inst: object, value: object) -> None
    def __delete__(self, inst: object) -> None   # AttributeError
    def default_value(self, inst: object | None = None) -> object
    def coerce(self, value: object, inst: object | None = None) -> object
    def read_raw(self, inst: object) -> object       # storage value (no wrap, no callbacks); default if absent
    def write_raw(self, inst: object, value: object) -> None   # writes without callbacks/dirtiness (state restoration)
    def to_rna_dict(self) -> dict[str, object]
    def clone_for(self, owner: type) -> "PropertyDef"
class BoolDef(PropertyDef): default: bool | tuple
class IntDef(PropertyDef): default: int | tuple; hard_min: int; hard_max: int; soft_min: int; soft_max: int; step: int
class FloatDef(PropertyDef): default: float | tuple; hard_min: float; hard_max: float; soft_min: float; soft_max: float; step: float; precision: int
class StringDef(PropertyDef): default: str; maxlen: int; search: Callable | None; search_options: frozenset[str]
class EnumDef(PropertyDef):
    default: str | frozenset[str] | int | None; is_dynamic: bool
    def items_for(self, inst: object | None, context: object | None = None) -> tuple[EnumItem, ...]
class PointerDef(PropertyDef):
    fixed_type: type; poll: Callable | None
    is_id_pointer: bool          # getattr(fixed_type, "_q_is_id", False)
    counts_user: bool; on_remove: str
class CollectionDef(PropertyDef): fixed_type: type
def build_property(identifier: str, deferred: "_PropertyDeferred", owner: type) -> PropertyDef
```

**Construction** (`build_property`): validates everything; any problem raises
`RegistrationError(f'bpy_struct "{owner.__name__}" registration error: \'{identifier}\' {Factory} could not register')`
with `__cause__` = the specific error **[O]**. Rules: options outside `OPTION_FLAGS` (or `ENUM_FLAG` outside
Enum); default with the wrong type/size; static enum whose `default` is not in the items; `ENUM_FLAG` with a
default that is not a `set`; `PointerProperty(type=X)` where `X` is not a subclass of `Struct` with
`bl_rna` in its **own** `__dict__` (registered PropertyGroup or built-in struct, e.g. `RenderSettings`)
**nor** an ID class (`_q_is_id`); `CollectionProperty(type=X)` where `X` has no own `bl_rna`. A pointer
to a non-ID struct behaves like a pointer to a PropertyGroup (lazily created instance,
read-only).
Limits: `soft_min = max(soft_min given or hard_min, hard_min)`, `soft_max = min(soft_max given or
hard_max, hard_max)`; a default outside `[min, max]` is clamped.

**Storage** (on the owner): scalars in `inst._p[identifier]` (`bool`, `int`, `float` already in float32,
`str`); enum: `str` identifier (flag: `frozenset[str]`); arrays: `np.ndarray` (`bool_`/`int32`/
`float32`, shape `size`); pointer to ID: the instance (strong); pointer to PropertyGroup: instance
created **lazily** on the 1st read (`fixed_type._q_new_child(owner=inst, path=identifier)`) and
stored; collection: `GroupCollection` created lazily and stored.

**Read** `__get__(inst)`:
1. `inst is None` → returns `self.deferred` if it exists, otherwise `self` (access through the class returns
   the `_PropertyDeferred` **[O]**).
2. `meta["virtual_get"]` → `v = virtual_get(inst)`; array → `hooks.wrap_array(np.asarray(v), self, inst,
   on_write)` where `on_write` calls `virtual_set(inst, view)` (or raises `ReadOnlyError` if there is none);
   scalar `FLOAT` → `to_float32`; others as they came.
3. User `get` → `raw = get(inst)` (enum: `int` → identifier of the item with that value; flag: bitmask →
   `set`); then `get_transform(inst, value, is_set)` if present.
4. Otherwise: stored value or default (arrays: materializes the default in `_p` **without** marking it as set,
   so that the wrap writes to persistent storage); `get_transform` if present.
5. Arrays return `hooks.wrap_array(view, self, inst, on_write=<per-component write>)`. Enum flag
   returns a new `set`. Pointer to PG/collection returns the stored instance.

**Write** `__set__(inst, value)`, in this order **[O]**:
1. read-only, pointer to PropertyGroup or collection → `ReadOnlyError(f'bpy_struct: attribute "{identifier}" from "{type(inst).__name__}" is read-only')`;
2. `v = self.coerce(value, inst)` (errors below);
3. `set_transform(inst, v, current, is_set)` if present (result coerced again);
4. writes: user `set` (`set(inst, raw)` with enum → item `int`, flag → bitmask, array → `tuple`
   (2D: tuple of tuples)), or `virtual_set(inst, v)`, or storage (existing arrays of the same shape
   are updated **in place** with `np.copyto`, so that live wrappers see the change);
5. `inst._p_set` receives the identifier;
6. `inst._q_on_change(self)` (if the owner has the method);
7. `hooks.on_property_changed(inst, self)`;
8. `update(inst, hooks.current_context())` if present — **always**, even with no value change and after
   clamping **[O]**; callback exception: traceback on `stderr`, does not propagate **[I]**.

Per-component writes through the wrapper (`ob.location.x = 1`) run steps 4–8 over the whole array (re-clamping in place).

**Coercion** (message prefix: `"bpy_struct: item.attr = val: "` **[O]**; `T` = name of the owner's class):

| Type | Accepts | Rejects (message contains) |
|---|---|---|
| BOOLEAN | `bool`, `np.bool_`, `int` 0/1 **[O]** | other ints: `f"{T}.{id} expected True/False or 0/1, not int"`; others: `PropertyTypeError` |
| INT | `int`, `bool` (becomes 0/1) **[O]**, `np.integer`; clamps to `[hard_min, hard_max]` | `float` (even `2.0`): `f"{T}.{id} expected an int type, not float"` **[O]** |
| FLOAT | `int`, `float`, `bool`, real `np.number`; clamps; rounds to float32 | `str` etc.: `f"{T}.{id} expected a float type, not {type}"` |
| STRING | `str` (subtype `BYTE_STRING` also `bytes`); `maxlen>0` truncates to ≤ `maxlen` UTF-8 **bytes** at a character boundary **[O]** | `f"{T}.{id} expected a string type, not {type}"` |
| ENUM | identifier present in `items_for(inst, context)` | `f'enum "{v}" not found in ({list})'` with `list = ", ".join(repr(i) for i in ids)` **[O]** |
| ENUM flag | `set`/`frozenset` of valid identifiers | non-set: `"expected a set"`; invalid: as above |
| POINTER (ID) | `None` or `isinstance(v, fixed_type)`; `poll(inst, v)` false → `PropertyValueError` | `f"{T}.{id} expected a {fixed_type.__name__} type, not {type(v).__name__}"` **[O]**; removed ID → `RemovedStructError` |
| arrays | iterable (not `str`) with `array_length` elements (2D accepts nested or flat); element coerced like the scalar | size: `PropertyValueError(f"bpy_struct: item.attr = val: sequences of dimension 0 should contain {n} items, not {m}")` **[O]** |

**`to_rna_dict()`** (same schema as the prop entries of `data/blender_api_dump.json`): keys `type`,
`subtype`, `unit` (only `FLOAT` with unit ≠ `NONE`), `flags` (list in the canonical order `is_readonly,
is_animatable, is_hidden, is_skip_save, is_never_none, is_registered, is_registered_optional,
is_enum_flag`; tests compare as a set), `array_length` and `array_dimensions` (arrays only; the
second only for 2D), `default` (scalar or flat list), `min/max/soft_min/soft_max/step` (INT/FLOAT;
FLOAT rounded to float32, e.g. `1e12 → 999999995904.0`), `precision` (FLOAT), `items` (static
ENUM: list of identifiers), `length_max` (STRING with `maxlen>0`), `fixed_type` (POINTER/
COLLECTION: `meta["fixed_type_name"]` or `fixed_type.bl_rna.identifier`).

#### 1.6.5 `quartz/rna/collections.py`

```python
class PropCollection:                        # = bpy_prop_collection (base of ALL RNA collections)
    def __init__(self, *, owner: object = None, path: str = "") -> None
    def _q_items(self) -> Sequence[object]   # abstract: items in public order
    def _q_key(self, item: object) -> str | None    # default: getattr(item, "name", None)
    def __len__(self) -> int
    def __iter__(self) -> Iterator[object]
    def __getitem__(self, key: int | str | slice) -> object
        # int (negatives ok; IndexError); str -> KeyError(f'bpy_prop_collection[key]: key "{key}" not found') [O]; slice -> list
    def __contains__(self, key: object) -> bool     # str: key; otherwise: item identity
    def get(self, key: str, default: object = None) -> object
    def find(self, key: str) -> int                 # index or -1
    def keys(self) -> list[str]; def values(self) -> list[object]; def items(self) -> list[tuple[str, object]]
    def foreach_get(self, attr: str, seq: MutableSequence | np.ndarray) -> None
    def foreach_set(self, attr: str, seq: Sequence | np.ndarray) -> None
        # generic: flattens/unflattens getattr/setattr per item; wrong size -> PropertyValueError("foreach_get/set: sequence size mismatch") [I];
        # accepts list or ndarray of any dtype (cast); subclasses MAY have a fast path
    rna_type: "RNAStruct"; id_data: object | None
    def path_from_id(self) -> str
    def __repr__(self) -> str        # f"<bpy_collection[{len(self)}], {type(self).__name__}>" [O]
    def __bool__(self) -> bool       # len > 0
class GroupCollection(PropCollection):     # value of CollectionProperty
    item_type: type
    def __init__(self, item_type: type, *, owner: object, path: str) -> None
    def add(self) -> object                 # new PropertyGroup (owner = owner of the collection, path = f"{path}[{i}]"); marks the prop as set
    def remove(self, index: int) -> None    # IndexError when out of range; reindexes the paths
    def clear(self) -> None
    def move(self, from_index: int, to_index: int) -> None
class PropArray:                            # = bpy_prop_array
    def __init__(self, values: np.ndarray, *, on_write: Callable[[], None] | None = None, owner: object = None, pdef: object = None) -> None
    def __len__(self) -> int                # first dimension
    def __iter__(self) -> Iterator          # Python scalars (bool/int/float) or sub-PropArray (2D)
    def __getitem__(self, index: int | slice) -> object     # slice -> tuple
    def __setitem__(self, index: int | slice, value: object) -> None   # writes to the view and calls on_write
    def __eq__(self, other: object) -> bool  # element-wise equality with any sequence of the same length
    def __array__(self, dtype=None, copy=None) -> np.ndarray
    def foreach_get(self, seq) -> None; def foreach_set(self, seq) -> None
    def q_to_list(self) -> list
    def __repr__(self) -> str                # f"<bpy_prop_array[{len}], {T}.{identifier}>" [I]
```

#### 1.6.6 `quartz/rna/annotations.py`

```python
def own_annotations(klass: type) -> dict[str, object]
    # Python 3.14: annotationlib.get_annotations(klass, format=Format.VALUE); if it raises, Format.FORWARDREF;
    # strings/ForwardRef are evaluated with eval(text, vars(sys.modules[klass.__module__]), dict(vars(klass))); failure -> ignored.
    # Without annotationlib: klass.__dict__.get("__annotations__", {}). NEVER reassign __annotations__.
def collect_annotations(cls: type) -> dict[str, "_PropertyDeferred"]
    # walks reversed(cls.__mro__) skipping `object` and classes with "_q_builtin" True in their OWN __dict__ (except cls);
    # keeps only _PropertyDeferred values; subclass overrides base/mixin
def install_properties(cls: type) -> list["PropertyDef"]
    # build_property for each collected annotation + type.__setattr__(cls, name, pdef); atomic (failure removes the ones already installed and re-raises);
    # stores the list of names in cls.__dict__["_q_installed"]
def uninstall_properties(cls: type) -> None          # removes the ones installed by install_properties (the dynamic ones too)
def define_property(cls: type, identifier: str, deferred: "_PropertyDeferred") -> "PropertyDef"
    # dynamic extension (StructMeta.__setattr__); stores in cls.__dict__["_q_dynamic"]; calls hooks.on_type_property_defined
def remove_property(cls: type, identifier: str) -> None
    # AttributeError if cls.__dict__ has no PropertyDef with that name; calls hooks.on_type_property_removed
def get_property(cls_or_inst: type | object, identifier: str) -> "PropertyDef | None"   # searches the __dict__s of the MRO
def iter_properties(cls_or_inst: type | object) -> Iterator["PropertyDef"]
    # order: base first (declaration order), dynamic ones at the end in definition order; a shadowed name appears once (most derived version)
```

Old-style assignment in the class body (`x = IntProperty()`) does **not** create a property **[O]** (it stays an
ordinary attribute). Values stored on instances survive `remove_property`/`define_property` again (storage
is keyed by identifier).

#### 1.6.7 `quartz/rna/struct.py`

```python
class IDRef(NamedTuple):
    target: object                       # the referenced ID
    owner: object                        # the Struct that holds the reference
    kind: str                            # "POINTER" | "DATA" | "COLLECTION_OBJECT" | "COLLECTION_CHILD" | "MATERIAL" | "WORLD" | "WINDOW_SCENE" | other
    counts_user: bool
    on_remove: str                       # "CLEAR" | "DELETE_OWNER"
    clear: Callable[[], None]            # undoes the reference
    remap: Callable[[object], None]      # swaps the target

class StructMeta(type):
    def __setattr__(cls, name: str, value: object) -> None
        # value is _PropertyDeferred and "bl_rna" in cls.__dict__ -> define_property; otherwise type.__setattr__
    def __delattr__(cls, name: str) -> None
        # PropertyDef in cls.__dict__[name] -> remove_property; otherwise type.__delattr__
    @property
    def is_registered(cls) -> bool       # "bl_rna" in cls.__dict__ [O][L]

def builtin_struct(cls: type | None = None, *, identifier: str | None = None)
    # decorator (with or without arguments): install_properties(cls); cls._q_builtin = True (in its own __dict__);
    # cls.bl_rna = RNAStruct(cls, identifier or cls.__name__); returns cls

MISSING: object                          # sentinel

@builtin_struct
class Struct(metaclass=StructMeta):      # = bpy_struct
    _q_strict_attrs: ClassVar[bool] = False    # True on built-in data types (IDs, mesh elements, scene structs)
    _q_is_id: ClassVar[bool] = False
    def __new__(cls, *args, **kwargs) -> "Struct"    # object.__new__(cls) + state: _p = {}, _p_set = set(), _q_idprops = None,
                                                       # _q_owner = None, _q_path = "", _q_key_order = []
    def __init__(self, *args, **kwargs) -> None       # accepts and ignores
    rna_type: "RNAStruct"                     # property: type(self).bl_rna
    id_data: object | None                    # property: self if _q_is_id; otherwise walks up _q_owner until an ID is found; None if there is none
    def __setattr__(self, name: str, value: object) -> None
        # data descriptor in the MRO -> descriptor; name starting with "_" -> object.__setattr__;
        # _q_strict_attrs -> AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'") [O]; otherwise object.__setattr__
    def __repr__(self) -> str
        # with id_data and path: f"{repr(id_data)}.{path_from_id()}" [O: "bpy.data.scenes['Scene'].qz_attr_pg"];
        # otherwise f"<bpy_struct, {type(self).__name__} at 0x{id(self):016X}>"
    def as_pointer(self) -> int                # id(self)
    def path_from_id(self, property: str = "") -> str
        # path from the owning ID (joins the _q_path of the chain with "."); ID: "" or the prop itself;
        # no owning ID -> ValueError(f"{type(self).__name__}.path_from_id() does not support path creation for this type") [I]
    def path_from_module(self, property: str = "", index: int = -1) -> str   # full f"{hooks.repr_root()}.data...."
    def path_resolve(self, path: str, coerce: bool = True) -> object        # datapath.resolve(self, path, coerce=coerce)
    def is_property_set(self, property: str, ghost: bool = True) -> bool    # property in _p_set (or idprop key)
    def property_unset(self, property: str) -> None                          # removes from _p and _p_set (goes back to the default) [O]
    def is_property_readonly(self, property: str) -> bool
    def is_property_hidden(self, property: str) -> bool
    def is_property_overridable_library(self, property: str) -> bool        # False
    def property_overridable_library_set(self, property: str, overridable: bool) -> bool   # True, no effect
    def keys(self) -> list[str]
        # ID (_q_is_id): idprop keys only [O]; PropertyGroup instance: written RNA props + idprop keys, in the order of the
        # FIRST write (_q_key_order) [O]; other Structs: idprops only
    def values(self) -> list[object]; def items(self) -> list[tuple[str, object]]
    def get(self, key: str, default: object = None) -> object
    def pop(self, key: str, default: object = MISSING) -> object
    def __getitem__(self, key: str) -> object        # KeyError(f'bpy_struct[key]: key "{key}" not found') [O]
    def __setitem__(self, key: str, value: object) -> None   # idprop (PropertyGroup + RNA prop name -> setattr)
    def __delitem__(self, key: str) -> None
    def __contains__(self, key: str) -> bool         # key in keys()
    def id_properties_ensure(self) -> "IDPropertyGroup"
    def id_properties_clear(self) -> None
    def id_properties_ui(self, key: str) -> "IDPropertyUIManager"   # KeyError if the key does not exist
    def bl_system_properties_get(self, *, do_create: bool = False) -> "IDPropertyGroup | None"   # copy of the written RNA values
    def type_recast(self) -> "Struct"                # self
    def rna_ancestors(self) -> list["Struct"]        # from the owning ID to the immediate parent
    @classmethod
    def bl_rna_get_subclass(cls, id: str, default: object = None) -> object       # RNAStruct of a subclass (recursive, ignores tombstones) with that identifier
    @classmethod
    def bl_rna_get_subclass_py(cls, id: str, default: object = None) -> object    # the corresponding Python class
    def keyframe_insert(self, data_path: str, index: int = -1, frame: float | None = None, group: str = "",
                        options: set[str] = frozenset(), keytype: str = "KEYFRAME") -> bool   # NotImplementedInQuartz(f"bpy_struct.keyframe_insert")
    def keyframe_delete(self, data_path: str, index: int = -1, frame: float | None = None, group: str = "") -> bool  # same
    def driver_add(self, path: str, index: int = -1) -> object      # NotImplementedInQuartz("bpy_struct.driver_add")
    def driver_remove(self, path: str, index: int = -1) -> bool     # False
    # ---- internal protocol used by Layer 2 ----
    def _q_on_change(self, pdef: "PropertyDef") -> None   # default: if id_data is neither None nor self -> id_data._q_on_change(pdef)
    def _q_refs(self) -> Iterator[IDRef]
        # generic: for each ID PointerDef with a non-None value (counts_user/on_remove from the PointerDef);
        # recursive into pointers to PropertyGroup and collection items. Subclasses EXTEND (super() + extras).
    def _q_state_get(self) -> dict
        # {"p": {id: deep copy (arrays copied; nested PG -> its _q_state_get(); collection -> list of states)},
        #  "set": sorted(_p_set), "idprops": to_dict() or None, "order": list(_q_key_order)}
        # Allowed values (for the .qz): None, bool, int, float, str, list, tuple, dict(str->...), set/frozenset, np.ndarray,
        # ID instances (references). Subclasses EXTEND with their own keys.
    def _q_state_set(self, state: dict) -> None          # restores IN PLACE (nested PGs reused; collection items recreated)
    @classmethod
    def _q_new_child(cls, owner: "Struct", path: str) -> "Struct"
    def _q_set_owner(self, owner: "Struct | None", path: str) -> None

@builtin_struct
class PropertyGroup(Struct):
    _q_registrable: ClassVar[bool] = True
    name: StringProperty(name="Name", description="")     # implicit prop [O]
```

User classes (Operator, Panel, PropertyGroup…) do NOT use `_q_strict_attrs` (assigning an unknown
attribute to a PropertyGroup instance is accepted **[O]**).

#### 1.6.8 `quartz/rna/idprops.py`

```python
class IDPropertyGroup(MutableMapping[str, object]):      # = idprop.types.IDPropertyGroup
    name: str
    def __init__(self, data: Mapping[str, object] | None = None, *, name: str = "", owner: object = None) -> None
    # __getitem__ (KeyError), __setitem__, __delitem__, __iter__ (insertion), __len__, __contains__, keys/values/items/get/pop/clear/update
    def to_dict(self) -> dict[str, object]                # recursive; arrays -> lists
class IDPropertyArray:                                    # = idprop.types.IDPropertyArray
    typecode: str                                         # "i" (int32) | "d" (double) | "b" (bool)
    def __init__(self, values: Iterable, typecode: str) -> None
    # __len__, __getitem__, __setitem__ (coerces to the typecode), __iter__, __eq__ (with sequences), __array__
    def to_list(self) -> list
class IDPropertyUIManager:
    def __init__(self, group: IDPropertyGroup, key: str) -> None
    def update(self, *, subtype: str | None = None, min: object = None, max: object = None, soft_min: object = None,
               soft_max: object = None, precision: int | None = None, step: object = None, default: object = None,
               description: str | None = None, id_type: str | None = None, items: object = None) -> None
               # kwarg incompatible with the value type (e.g. precision on an int) -> TypeError
    def as_dict(self) -> dict[str, object]
    def clear(self) -> None
    def update_from(self, ui_manager: "IDPropertyUIManager") -> None
def rna_idprop_ui_create(item: object, prop: str, *, default: object, min: object = 0, max: object = 1,
                         soft_min: object = None, soft_max: object = None, description: str | None = None,
                         overridable: bool = False, subtype: str | None = None, step: object = None,
                         precision: int | None = None, id_type: str | None = None, items: object = None) -> IDPropertyUIManager
                         # item[prop] = default; soft_* default to min/max
def rna_idprop_value_to_python(value: object) -> object     # group -> dict; array -> list; rest unchanged
def rna_idprop_quote_path(prop: str) -> str                 # f'["{escape_identifier(prop)}"]'
```

Conversion on assignment: `bool` → bool; `int` → int (outside int32 → `OverflowError` **[I]**); `float` →
**double** (idprops do not round to float32); `str`; sequence of numbers → `IDPropertyArray` (`"i"` if
all int, `"b"` if all bool, otherwise `"d"`) **[O type]**; `dict` → nested `IDPropertyGroup` **[O]**;
list of dicts → list of groups; ID instance → reference; anything else → `TypeError`. `as_dict()` of a
float after `update(min=0, max=10)` == `{"subtype": "NONE", "description": "", "min": 0.0, "max": 10.0,
"soft_min": 0.0, "soft_max": 10.0, "step": 1.0, "precision": 3, "default": 0.0}` **[O]**. Defaults
when not set: FLOAT `min/soft_min = -3.4028234663852886e38`, `max/soft_max = +…`, `step 1.0`,
`precision 3`, `default 0.0`; INT `min/soft_min = -2**31`, `max/soft_max = 2**31-1`, `step 1`,
`default 0`; STRING `{"subtype": "NONE", "description": "", "default": ""}` **[I]**.

#### 1.6.9 `quartz/rna/rnainfo.py`

```python
class RNAEnumItem: identifier: str; name: str; description: str; icon: str; value: int
class RNAProperty:                       # read-only view of a PropertyDef (or of the "rna_type" pseudo-prop)
    identifier: str; name: str; description: str; translation_context: str
    type: str; subtype: str; unit: str; icon: str; tags: frozenset[str]
    is_readonly: bool; is_hidden: bool; is_skip_save: bool; is_animatable: bool; is_enum_flag: bool
    is_never_none: bool; is_library_editable: bool; is_overridable: bool; is_registered: bool
    is_registered_optional: bool; is_required: bool; is_argument_optional: bool; is_output: bool; is_runtime: bool
    default: object; default_array: tuple; array_length: int; array_dimensions: tuple[int, ...]
    hard_min: float; hard_max: float; soft_min: float; soft_max: float; step: float; precision: int
    length_max: int; enum_items: PropCollection; enum_items_static: PropCollection
    fixed_type: "RNAStruct | None"
    q_definition: "PropertyDef | None"
class RNAStruct:                         # = cls.bl_rna
    def __init__(self, py_class: type, identifier: str | None = None) -> None
    identifier: str                      # RNA name
    name: str                            # getattr(cls, "bl_label", identifier)
    description: str                     # 1st line of the class docstring or ""
    translation_context: str             # "*"
    base: "RNAStruct | None"             # bl_rna of the nearest base that has bl_rna
    nested: None
    properties: PropCollection           # LIVE: "rna_type" pseudo-prop + iter_properties(py_class) [O]
    functions: PropCollection            # empty in user classes
    q_py_class: type
    def __repr__(self) -> str            # f'<bpy_struct, Struct("{identifier}") at 0x...>'
```

#### 1.6.10 `quartz/rna/description.py`

```python
class Description:
    owner: type
    def __init__(self, owner: type) -> None
    def __iter__(self) -> Iterator["PropertyDef"]; def __len__(self) -> int
    def __contains__(self, identifier: str) -> bool; def __getitem__(self, identifier: str) -> "PropertyDef"   # KeyError
    def groups(self) -> tuple[str, ...]                 # distinct values of meta["group"] in order ("" = no group)
    def in_group(self, group: str) -> tuple["PropertyDef", ...]
    def children_of(self, identifier: str) -> tuple["PropertyDef", ...]   # meta["parent"] == identifier
    def is_enabled(self, inst: object, identifier: str) -> bool
        # meta["enabled_if"](inst) if callable; otherwise, if meta["parent"] is BOOLEAN: bool(getattr(inst, parent)); otherwise True
    def is_visible(self, inst: object, identifier: str) -> bool   # meta["visible_if"](inst) if callable; otherwise not is_hidden
    def to_rna_dict(self) -> dict[str, dict]
def describe(cls_or_inst: type | object) -> Description
```

### 1.7 Architecture tests (`l1-scaffold-app`)

- `tests/arch/test_headers.py`: every `.py` under `quartz/`, `compat/`, `tools/`, `tests/` (ignoring
  `__pycache__`) satisfies §0.1(1): it parses, and has no comments and no docstrings.
- `tests/arch/test_layering.py`: parses with `ast` (module-level imports **and** imports inside functions;
  relative imports resolved by module name) the existing files of `quartz/` and `compat/` and applies §0.5.
  "stdlib" = `sys.stdlib_module_names`; "shims" = `{bpy, mathutils, bmesh, bpy_extras, addon_utils, idprop,
  rna_prop_ui, bl_math, bl_ui, bl_operators, gpu, gpu_extras, blf, aud, bl_ext}`. Missing files are
  ignored (the test grows with the project). Fails listing each violation as `file:line module`.
- `tests/arch/test_cleanroom.py`: no file in `quartz/`, `compat/`, `tools/` contains (case-insensitive)
  `SPDX-License-Identifier`, `GNU General Public License`, `Copyright (C) Blender`,
  `Copyright Blender`, `Maxon Computer`, `All rights reserved`.

---

## 2. Layer 2 — Model and runtime

### 2.0 Overview and L2 gate

Layer 2 is the `bpy`-shaped data model (IDs, scene, data-blocks and depsgraph), the class
registry with the headless UI, the runtime (session, context, operator calls, undo and the
`.qz` file) and the built-in operators. It imports L1 and L2 (§0.5); never L3, not even inside functions.

#### 2.0.1 Tasks, sections and dependencies

| Section | Task | Modules | Uses from L2 |
|---|---|---|---|
| §2.2 | `l2-idmodel` | `quartz.types` (package), `quartz.types.naming/id/blenddata/object/collection/scene/world/wm`, `quartz.depsgraph` | nothing (L1 only) |
| §2.3 | `l2-datablocks` | `quartz.types.mesh/material/camera/light/image/text` | `quartz.types.id`, `quartz.types.blenddata`, `quartz.types.object` (§0.6) |
| §2.5 | `l2-registry-ui` | `quartz.registry`, `quartz.types.operator/ui/prefs/stubs`, `quartz.ui`, `quartz.utils` (+ `previews`, `units`) | nothing (L1 only) |
| §2.6 | `l2-runtime` | `quartz.session`, `quartz.contexts`, `quartz.ops`, `quartz.undo`, `quartz.io` (+ `state`, `qzfile`), `quartz.testing` | all |
| §2.7 | `l2-operators` | `quartz.operators` | all |

§2.0, §2.1 (cross-cutting protocols) and §2.4 (schema conformance) do not belong to any
task (they have no code files): they apply to all L2 and L3 tasks.

Dependency rules:

1. `l2-idmodel` and `l2-registry-ui` do not import each other. The two links the rest needs
   are installed by the integrator `l2-runtime` in `quartz.session.install_hooks()` (§2.1.1):
   `quartz.types.set_name_resolver(quartz.registry.lookup)` (registered RNA names visible in
   `quartz.types`, §0.3) and the `current_context` hook (used by idmodel and registry-ui without importing
   the session). Single exception: `quartz.types.load_builtin_types()` loads through `importlib` the modules
   in `BUILTIN_TYPE_MODULES` (including those of `l2-datablocks`, `l2-registry-ui` and
   `quartz.contexts`, from `l2-runtime`), tolerating absence (§2.2.1, rule 1); no other code of
   `l2-idmodel` imports them.
2. `quartz/types/__init__.py` loads the type modules lazily and tolerates a missing
   sibling (ARCHITECTURE §14); therefore the package can be imported before all the tasks
   exist.
3. Inside `quartz/**`, type imports MUST use the explicit module
   (`from quartz.types.object import Object`). `quartz.types.<Name>` (via `__getattr__`) is for
   user code, compat and tests.
4. Tests of `l2-idmodel`, `l2-datablocks` and `l2-registry-ui` MUST run without `quartz.session` and
   without `quartz.testing`, with local fixtures (`BlendData()` directly; hooks installed with
   `quartz.types.install_hooks()`, `quartz.registry.install_hooks()` or `hooks.install(...)` between
   `hooks.snapshot()` and `hooks.restore()`), except the schema tests (§2.4). `l2-runtime` and
   `l2-operators` use the `qz`/`qz_empty` fixtures (§1.1.2), and every test that touches the session MUST
   go through them (they restore the global state, §2.6.8).

#### 2.0.2 Import effects allowed in Layer 2 (closed list; complements §0.1(4))

| Import | Effect |
|---|---|
| `quartz.types.object`, `collection`, `scene`, `world`, `wm`, `mesh`, `material`, `camera`, `light`, `image`, `text` | `register_id_type(...)` at the end of the module; `mesh`, `camera`, `light` also `register_object_data_type(...)` |
| `quartz.registry` | `register_base(quartz.rna.PropertyGroup)` |
| `quartz.types.operator`, `quartz.types.ui`, `quartz.types.prefs`, `quartz.types.stubs` | `register_base(...)` of the registrable bases defined in the module (§2.5.1) |

No other L2 module has an import effect. In particular, **no import installs hooks** from
`quartz.rna.hooks` (the L1 tests depend on the defaults of §1.6.2 and pytest runs
`tests/unit/operators` and `tests/unit/registry` before `tests/unit/rna`): the L2 hooks are only
installed by `quartz.session.install_hooks()`, called by `quartz.session.current()` and by
`Session.reset()` (§2.1.1). The session is only born in `current()` (first access to
`quartz.data`/`quartz.context` or an explicit call).

#### 2.0.3 General rules of Layer 2

1. **Stable identity**: the same data always returns the same Python object
   (`data.objects["Cube"] is data.objects["Cube"]`; divergence 4 of ARCHITECTURE §13). The `Session`
   and its members (`data`, `wm`, `preferences`, `context`, `undo`) are never recreated (D14).
2. **Built-in types** are `@builtin_struct` (§1.6.7) with `_q_strict_attrs = True` (unknown
   attribute → `AttributeError` **[O]**). Registrable bases and their user subclasses are not
   strict.
3. **Built-in properties** use the factories of `quartz.props` (D3) with the name, type, subtype,
   unit, size, default, limits and items from the dump (§2.4). Computed props use
   `meta={"virtual_get": ..., "virtual_set": ...}`; the dirty channel of each prop comes from
   `meta["dirty"]` (§2.2.3).
4. **Prefixes** `q_` (public, Quartz-only) and `_q_` (internal) on every bpy-shaped type (§0.2).
5. **Not implemented** raises `NotImplementedInQuartz(<Blender symbol>)`, for example
   `"ID.animation_data_create"` or `"bpy.data.actions.new"`.
6. **Determinism**: no structure depends on the wall clock; `session_uid` and the dirty clock
   (§2.2.3) are process counters, monotonic, never reset by `reset`.
7. **Float32 at rest** and float64 arithmetic (§0.2).
8. **Missing log**: L2 code that serves a "ghost" surface (a `bpy.data` collection that is not
   implemented, an unknown `UILayout` function, a context member that Blender fills and Quartz does not)
   calls `quartz.rna.hooks.note_missing(<Blender name>)`, for example
   `"bpy.data.actions"`, `"bpy.types.UILayout.template_xyz"`, `"bpy.context.asset_library_reference"`.
9. **[L] mark** (applies to Layers 2 and 3): behavior deduced from reading the Python modules
   that ship with Blender 5.2.2, described in our own words; for the implementer it counts as
   **[I]** (a future golden or probe prevails).

#### 2.0.4 Map of the ARCHITECTURE references

ARCHITECTURE was written before this numbering; where it cites:

- §7.1 "CONTRACTS §2.3" (registration rules) → §2.5.1, with the sequence in §2.1.6;
- §7.2 "CONTRACTS §2.5" (operator sequence and messages) → §2.5.2 (`Operator` class) and §2.6.3
  (`quartz.ops`), with the sequence in §2.1.8;
- §10 "CONTRACTS §3.5" (CLI) → §3.5 (correct).

#### 2.0.5 L2 gate

Layer 2 is ready when, from the project root:

1. `.venv/Scripts/python.exe -m pytest -q` passes in full (L1, L2 and `tests/arch/*`; `blender`,
   `sweep` and `corpus` tests skipped by default).
2. `tests/arch/test_layering.py` reports no L3 import in L2 nor L2 import in L1.
3. The factory scene reproduces the facts of §2.6.1 (`l2-runtime` tests).
4. The schema tests (§2.4) pass for all built-in types and operators, with the
   divergences listed.
5. The native flow (`tests/unit/runtime/test_native_flow.py`) passes: an add-on written with `quartz` only
   declares a `PropertyGroup`, an `Operator` and a `Panel`; registers with
   `quartz.utils.register_class`; attaches a `PointerProperty` to `Scene`; calls the operator through
   `quartz.ops`; draws the panel with `quartz.ui.draw_ui`; unregisters; and nothing is left registered or
   hanging off types — without `quartz.compat`.
6. No file outside the §0.4 table was created.

Tests that depend on a module from another task (§0.6) only need to pass at this gate.

### 2.1 Cross-cutting protocols of Layer 2

Normative for all L2 and L3 tasks. Each protocol has an owner that implements it (indicated) and
consumers that depend on it exactly as described here. Full signatures live in the
owners' sections; in case of divergence between this section and the owner's, this one wins.

#### 2.1.1 `quartz.rna.hooks` hooks and extension points

| Hook (§1.6.2) | Implemented in | Installed by | Implementation |
|---|---|---|---|
| `wrap_array` | `quartz.types.install_hooks()` (§2.2.1) | `quartz.session.install_hooks()` | `quartz.types.wrap_array`: subtype → `quartz.math` (table in §2.2.1) |
| `on_property_changed` | `quartz.types.install_hooks()` | same | `quartz.app.msgbus.notify_changed(inst, pdef.identifier)` |
| `on_type_property_defined`, `on_type_property_removed` | `quartz.registry.install_hooks()` (§2.5.1) | same | records/removes `(cls, identifier, deferred, current_owner())` for `type_props_owned_by` and `snapshot/restore` |
| `current_context` | `quartz.session.install_hooks()` (§2.6.1) | same | `quartz.session._current_context` (module function: `current().context`) — the real context, never the restricted one **[L]** |
| `note_missing` | `quartz.compat` (§3.1.1) | `quartz.compat.activate()`; restored by `deactivate()` | `quartz.compat.note_missing` |
| `repr_root` | `quartz.compat` | same | `lambda: "bpy"` |

Rules:

1. **No import installs hooks** (§2.0.2). `quartz.session.install_hooks()` — called by
   `quartz.session.current()` (on every call; idempotent) and by `Session.reset()` — calls
   `quartz.types.install_hooks()` and `quartz.registry.install_hooks()` and installs `current_context`.
2. Each `install_hooks()` function calls `hooks.install(...)` only with its own hooks and is
   idempotent; no module installs another owner's hook; `quartz.session.install_hooks()` does not
   touch `note_missing`/`repr_root`.
3. Tests that swap hooks MUST use `hooks.snapshot()`/`hooks.restore()`; L2 tests without a
   session install the hooks they need (`quartz.types.install_hooks()`,
   `quartz.registry.install_hooks()`) inside that pair. `quartz.testing.isolated` takes the snapshot
   before touching the session and restores it on exit (§2.6.8).
4. `quartz.session.install_hooks()` also installs two extension points that are not hooks of
   `quartz.rna.hooks`: `quartz.path.set_blend_filepath_provider(quartz.session._blend_filepath)`
   (module function: `current().data.filepath`; §1.1.6) and `quartz.types.set_name_resolver(quartz.registry.lookup)` (§2.2.1). The exit of
   `quartz.testing.isolated()` sets both back to `None`; `current()` reinstalls them on the next call.
5. Adapters installed by L3 (never by importing `quartz.*`; when, in §3.0.2):
   `quartz.math.bvhtree.set_object_adapter` (by `quartz.extras`, §3.2.1),
   `quartz.math.bvhtree.set_bmesh_adapter` and `quartz.types.mesh.set_editmode_hooks` (by
   `quartz.bmesh`, §3.3.1); `quartz.registry.set_missing_type_resolver` (by `quartz.compat`,
   §3.1.1). The exit of `quartz.testing.isolated()` sets the first three back to the default (`None` /
   no hooks).

#### 2.1.2 Handler dispatch

Always through `quartz.app.handlers.dispatch(name, *args)` (isolated exceptions, §1.2.2).

| Handler | Who dispatches | When | Arguments |
|---|---|---|---|
| `frame_change_pre`, `frame_change_post` | `Scene.frame_set` (§2.2.8) | before and after `depsgraph.update()`; at `pre`, `frame_current` is already the new one **[O]** | `(scene, depsgraph)` (at `pre` Blender delivers `depsgraph=None` **[O]**; Quartz passes the depsgraph — divergence of §2.2.8, rule 6) |
| `depsgraph_update_pre`, `depsgraph_update_post` | `Depsgraph.update` (§2.2.11), called by `ViewLayer.update`, `Scene.frame_set` and `Context.evaluated_depsgraph_get` | only when some ID changed since the last `update` **[O]** | `(scene, depsgraph)` **[O]** |
| `load_pre`, `load_post` | `quartz.io.load_qz` (§2.6.5) and `Session.reset` (§2.1.7) | before clearing / after assembling | `(filepath)`; `""` on reset **[I]** |
| `load_factory_startup_post` | `Session.reset` | after assembling the template, before `load_post` | `("",)` **[I]** |
| `load_post_fail` | `quartz.io.load_qz` | load failure | `(filepath)` |
| `save_pre`, `save_post`, `save_post_fail` | `quartz.io.save_qz` (§2.6.5) | before / success / failure | `(filepath)` |
| `undo_pre`, `undo_post`, `redo_pre`, `redo_post` | `UndoStack.undo` / `UndoStack.redo` (§2.6.4) | before and after applying the state | `(scene)`, the window's scene **[I]** |
| `startup_post`, `shutdown_pre`, `shutdown_post` | only `quartz.cli.main` (§3.5.1) | after creating the session / before exiting / after cleanup | `()` |
| `addon_enable_post`, `addon_disable_post` | only `quartz.addons` (§3.4.5) | after a successful `enable` / after `disable` of an enabled add-on (even with an error in `unregister`) | `(module_name)` |
| remaining names in `BLENDER_HANDLER_NAMES` | nobody in this milestone | — | — |

`Session.reset` and `load_qz` call `handlers.clear_non_persistent()` before `load_post`
(handlers without `@persistent` do not survive "open file") **[L]**.

#### 2.1.3 Fields of `quartz.app.settings`

| Field | Read by | Effect |
|---|---|---|
| `api_prefix` | `quartz.ops` and every error that cites `bpy.ops`/`bpy.data` | `"quartz"`; `"bpy"` with compat (switched by `quartz.compat.activate`) |
| `restrict_register` | `quartz.session.restrict_blend(enabled=None)` | turns on RestrictBlend in the add-on loader |
| `lenient_ui` | `quartz.compat.resolve_type` | synthesizes unknown UI names (and records them) |
| `record_missing` | `quartz.compat.note_missing` | `False` → does not record |
| `strict_layout` | `quartz.ui.UILayout.__getattr__` | unknown layout function → `AttributeError` instead of recording |
| `invoke_in_background` | `quartz.ops.call` | `INVOKE_*` calls `invoke()` (headless default: `execute()` **[O]**) |
| `sweep_mode` | `quartz.cli`, `quartz.sweep` | blocks network in the process (§3.0.6) |
| `trust_scripts` | `quartz.app.trusted()` | no mandatory consumer in this milestone |
| `undo_steps` | `UndoStack` (step limit); `PreferencesEdit.undo_steps` is a view of it | |

#### 2.1.4 IDs: users, references and removal

Owner: `l2-idmodel` (§2.2.4); each type emits its own `IDRef`s (§1.6.7) in `_q_refs`.

1. `ID.users` = sum of `counts_user` over all `IDRef`s whose `target` is the ID — walking all
   IDs in `BlendData` and the ones embedded by the owners — plus 1 if `use_fake_user` **[O]**. Derived on
   read (D7); never stored.
2. Reference table (normative):

| Reference | Emitted by | `kind` | `counts_user` | `on_remove` |
|---|---|---|---|---|
| `Object.data` | `Object` (§2.2.6) | `"DATA"` | `True` **[O]** | `"DELETE_OWNER"` **[O]** |
| `Object.parent` | `Object` | `"POINTER"` | `False` **[O]** | `"CLEAR"` |
| `Object.instance_collection` | `Object` | `"POINTER"` | `True` **[I]** | `"CLEAR"` |
| object linked to a collection (including the master one) | `Collection`; the master one by `Scene` | `"COLLECTION_OBJECT"` | `True` **[O]** | `"CLEAR"` (unlinks) |
| child collection linked (including in the master one) | `Collection`; the master one by `Scene` | `"COLLECTION_CHILD"` | `True` **[O]** | `"CLEAR"` |
| `Scene.world` | `Scene` (§2.2.8) | `"WORLD"` | `True` **[O]** | `"CLEAR"` |
| `Scene.camera` | `Scene` | `"POINTER"` | `False` **[O]** | `"CLEAR"` |
| `Mesh.materials[i]` | `Mesh` (§2.3.1) | `"MATERIAL"` | `True` **[O]** | `"CLEAR"` (the slot becomes `None`) |
| `Window.scene` | `WindowManager` (§2.2.10) | `"WINDOW_SCENE"` | `True` **[O]** | `"CLEAR"`: the window moves to another scene, or `None` **[I]** |
| `Camera.dof.focus_object` | `Camera` (§2.3.3) | `"POINTER"` | `False` **[I]** | `"CLEAR"` |
| `PointerProperty` to an ID without its own handling (built-in or add-on) | generic `Struct._q_refs` (§1.6.7) | `"POINTER"` | `meta["counts_user"]` (default `True` **[O]**) | `meta["on_remove"]` (default `"CLEAR"`) |

3. `IDCollection.remove(id, do_unlink=True, do_id_user=True, do_ui_user=True)`:
   1. ID already removed → `RemovedStructError` (the tombstone itself raises it) **[O]**.
   2. `do_unlink=False` with `users > 0` → `LinkError` with the fragment `"must have zero users to be
      removed"` **[I]**.
   3. For each `IDRef` in `BlendData.q_refs_to(id)`: `on_remove == "DELETE_OWNER"` → remove the owning
      ID by the same rule (removing the mesh removes the objects that use it **[O]**); otherwise
      `ref.clear()`.
   4. Removes it from the collection, `id._q_main = None`, `id._q_tombstone()`.
   5. The ID's own references disappear with it (`objects.remove(ob)` leaves the mesh orphaned with 0
      users **[O]**); children of the removed object end up with `parent = None`, without compensating the matrix
      **[I]**; affected collections stamp `"HIERARCHY"`.
4. **Tombstone**: `removed_class_for(cls)` swaps `__class__`; any non-dunder attribute access raises
   `RemovedStructError(f"StructRNA of type {RNA name} has been removed")` **[O]**, including a
   second `remove` **[O]**; the tombstone class has `_q_removed = True` (read by §1.4.1). Undo and
   state loading revive with `ID._q_revive(obj)`.
5. **Names** (§2.2.2): unique per collection with `.NNN`; the one being renamed gets the suffix **[O]**; cap of
   255 UTF-8 bytes **[O]**; empty → the type's `default_name` **[O]**; iteration by `sort_key`
   casefold, stable **[O]**.
6. **Copy**: `ID.copy()` → name `.NNN`, 0 users, in the same `bpy.data` collection, not linked
   to scene collections **[O]**; `Object.copy()` shares `data`; `Mesh.copy()` copies the geometry.
7. **`repr`**: `f"{hooks.repr_root()}.data.{collection}['{name}']"` (with compat:
   `"bpy.data.objects['Cube']"` **[O]**); master collection: `repr(scene) + ".collection"` **[O]**.

#### 2.1.5 State (`_q_state_get`/`_q_state_set`), `.qz` file and undo

Owner: `l2-runtime` (§2.6.6), with each type's keys specified by the type's owner.

1. Base: `Struct._q_state_get` (§1.6.7) uses `"p"`, `"set"`, `"idprops"`, `"order"`. `ID`
   adds only `"name"` (`use_fake_user`, `use_extra_user` and `tag` are stored `BoolProperty`s
   and travel in the generic `"p"`/`"set"`; there is no top-level copy that could
   diverge). Each type adds its own keys, without colliding with these, and lists them in its section; nested structs follow the generic one.
2. Allowed values: those of §1.6.7. A reference to an ID is the instance itself (in memory).
3. `_q_state_set(state)` restores in place, without calling `update`, handlers or msgbus.
   `quartz.io.state.apply` stamps `q_tag(*DIRTY_CHANNELS)` on each restored or created ID.
4. **Schema version**: each ID class has `q_schema_version` (default 1); the saved state
   carries `"schema"`; when applying an older state it chains `q_upgrade(state, v)` up to the current version
   (D16); a state newer than the class → `FileFormatError` with `"newer schema"`.
5. **JSON encoding** (`encode`/`decode`): ID instance → `{"__id__": n}` (index in `ids`);
   `np.ndarray` → `{"__array__": "<k>"}` with the array in `arrays/<k>.npy` (dtype and shape
   preserved); `tuple` → `{"__tuple__": [...]}`; `set`/`frozenset` → `{"__set__": [...]}`
   (sorted); non-finite float → `{"__float__": "nan" | "inf" | "-inf"}`; `dict` keys only
   `str` (anything else → `FileFormatError` on save); `"__…__"` keys reserved.
6. **Container** (zip, §2.6.7): `manifest.json` = `{"format": "quartz.qz", "format_version": 1,
   "quartz_version": "0.1.0", "author": "D1on1n", "ids": N}`; `data.json` = `{"state_version": 1,
   "ids": [{"type": <RNA name of the class>, "id_type": ..., "name": ..., "schema": ..., "state":
   ...}, ...], "extra": {...}}`; `arrays/<k>.npy` (`np.save`, loaded with
   `allow_pickle=False`). No timestamp; fixed order (IDs in the order of
   `BlendData.q_iter_ids()`). WindowManager, Screen and WorkSpace are not saved.
7. **Undo**: in-memory `capture`/`apply`; `IDState.instance` preserves identity; tombstones
   reverted; IDs created after the step are removed with a tombstone, no cascade; WindowManager,
   Screen and WorkSpace are left out.

#### 2.1.6 Class registration (sequence)

Owner: `l2-registry-ui` (§2.5.1). `register_class(cls)`:

1. `cls` is not a class or has no registrable base in its MRO → `RegistrationRuntimeError` with
   `"missing bl_rna attribute"` and `"(may not be registered)"` (Blender says `register_class(...):,
   missing bl_rna attribute from 'type' instance (may not be registered)` **[O]**).
2. Already registered (`"bl_rna" in cls.__dict__`) → `RegistrationError` with `"already registered as a
   subclass"` **[O]**.
3. Base validation: required attribute missing → `MissingClassAttributeError` with
   `f'class to have an "{attr}" attribute'` **[O]**; invalid class enum (`bl_space_type`,
   `bl_region_type`, `bl_options`) → `ClassValidationError` with `f'validating class: enum "{v}" not
   found in ('` **[O]**; invalid operator `bl_idname` → `RegistrationRuntimeError` with
   `"invalid bl_idname"` and the reason `"Must contain 1 '.' character"`, `"Invalid character at
   position {i}"` or `"Identifier too long, maximum length is 60"` **[O]** (without `bl_idname`, the class
   name applies **[O]**; leading digit accepted **[O]**); nonexistent `bl_parent_id` →
   `RegistrationRuntimeError` with `f"parent '{p}' for '{name}' not found"` **[O]**; name outside the
   `_PT_`/`_MT_`/`_HT_`/`_UL_` convention → only a warning on `stderr` **[O]**.
4. RNA name: operator → `operator_rna_name(bl_idname)` (`"mod.name"` → `"MOD_OT_name"` **[O]**);
   Panel/Menu/Header/UIList → `bl_idname` or the class name **[O]**; others → the base's rule
   (§2.5.1). Another class already registered with the same RNA name is unregistered first, silently
   **[O]**.
5. `install_properties(cls)`; a failure propagates the `RegistrationError` of §1.6.4 and nothing is left registered
   (atomic registration, divergence 1 of ARCHITECTURE §13).
6. Operator: creates the properties class (§2.5.2).
7. `cls.bl_rna = RNAStruct(cls, rna_name)`; indexes it; owner = `current_owner()`.
8. Calls the classmethod `cls.register()` if it exists **[O]**.
9. Notifies subscribers (`"register"`, `cls`).

`unregister_class(cls)`: not registered → `RegistrationRuntimeError` with `"missing bl_rna
attribute"` **[O]**; calls `cls.unregister()` if it exists **[O]**; removes props, `bl_rna`, indexes,
owner and properties class; functions attached (`append/prepend`) to the unregistered UI class
are discarded **[I]**; notifies (`"unregister"`, `cls`).

#### 2.1.7 Session: creation and reset (sequence)

Owner: `l2-runtime` (§2.6.1).

`quartz.session.current()` calls `install_hooks()` on every call (idempotent). On the first call:
`quartz.types.load_builtin_types()`; creates `BlendData`, `Preferences`, `Context`, `UndoStack` and the
`WindowManager` `"WinMan"` (linked to `data.window_managers`), which are the final identities; calls
`quartz.operators.register_builtin()` if the module exists; `reset(template="default")`. On later
calls it returns the same `Session`.

`Session.reset(template="default")`:

1. `template` not in `TEMPLATES` -> `ValueError`.
2. `install_hooks()` (reinstalls the L2 hooks; §2.1.1, rule 1).
3. `dispatch("load_pre", "")` **[I]**.
4. `handlers.clear_non_persistent()`; `timers.clear(keep_persistent=True)`; `msgbus.clear()` **[I]**.
5. `undo.clear()` (disabled); the context override stack is emptied.
6. `data.q_clear(keep=[wm])`: the WindowManager keeps its identity and keyconfigs; its windows are
   reduced to one.
7. `build_factory_scene(session)` or `build_empty_scene(session)`; the window points to the new
   scene, view layer, `Screen` and `WorkSpace`.
8. `data.q_set_filepath("")`; `data.q_mark_clean()`.
9. `dispatch("load_factory_startup_post", "")`; `dispatch("load_post", "")` **[I]**.

`restrict_blend()` swaps only the facades (`api_data()`/`api_context()`, therefore `quartz.data`,
`quartz.context`, `bpy.data`, `bpy.context`) for `RestrictedData`/`RestrictedContext`; the internal
context (operators, `current_context` hooks, `update` callbacks) remains the real one **[L]**.

#### 2.1.8 Operator call (sequence of `quartz.ops.call`)

Owner: `l2-runtime` (§2.6.3); consumes the `Operator` protocol (§2.5.2). `P` =
`settings.api_prefix`. `call(idname, *args, **kwargs)`:

1. Positionals: up to two — the execution context (`str` from `EXEC_CONTEXTS`) and `undo` (`bool`).
   A positional `dict`, or more than two -> `ExecContextError("1-2 args execution context is
   supported")` **[O]**; a string not in `EXEC_CONTEXTS` -> `PropertyTypeError` with
   `"expected a string enum in ("` **[I]**.
2. `cls = quartz.registry.operator_class(idname)`; missing ->
   `hooks.note_missing(f"bpy.ops.{idname}")` and `OperatorNotFoundError(f'Calling operator
   "{P}.ops.{idname}" error, could not be found')` **[O]**. `cls` a subclass of `quartz.types.stubs.Macro` ->
   `NotImplementedInQuartz("Macro operators")`, before `poll` (§2.5.5, rule 2; §2.6.3).
3. `ctx = quartz.session.current().context` (the real one, even under RestrictBlend).
4. `poll` (once; divergence 2 of ARCHITECTURE §13): if the class defines `poll`, `ok =
   cls.poll(ctx)` (exception in `poll`: traceback on `stderr` and counts as false **[I]**); false ->
   `PollFailedError(f"Operator {P}.ops.{idname}.poll() {msg}")`, `msg` = message from
   `poll_message_set` or `"failed, context is incorrect"` **[O]**. `poll` runs **before** the
   kwargs conversion **[O]**.
5. `op = cls()`; `op._q_assign(kwargs)` (`PropertyTypeError`/`PropertyValueError` errors with
   `"Converting py args to operator properties:"` **[O]**; out of range: silently clamped
   **[O]**). Values do not persist between calls (new instance) **[O]**.
6. Execution: `INVOKE_*` context and `settings.invoke_in_background` and the class has `invoke` ->
   `op.invoke(ctx, Event.q_synthetic())`; otherwise, if it has `execute` -> `op.execute(ctx)` (including with
   `INVOKE_DEFAULT` **[O]**); otherwise, if it has `invoke` -> `invoke`; otherwise `{"CANCELLED"}` **[I]**.
   Exception from user code -> `OperatorFailedError("Error: Python: " + traceback)` with the
   traceback in the text **[O]**.
7. Return: must be a `set`/`frozenset` of strings contained in `OPERATOR_RETURN_FLAGS`; otherwise
   `OperatorFailedError` with `"incompatible return value"` and `f"'{v}' not found in ("` (invalid
   value) or `"expected a set, not a NoneType"` (`None`) **[O]**.
8. Reports: `INFO`/`WARNING`/other non-error -> `stdout` as `f"{Type}: {message}"` **[I]**;
   if there is an `ERROR*` report -> `OperatorFailedError("Error: " + messages joined by "\n")` (**[O]**
   with `CANCELLED`, **[I]** with `FINISHED`).
9. `FINISHED`: `"UNDO" in bl_options` and `session.undo.enabled` and the positional `undo` is not `False` ->
   `session.undo.push(cls.bl_label)`; `"REGISTER" in bl_options` -> `session.wm.q_push_operator(op)`.
10. Returns a new `set` with the return value.

#### 2.1.9 Edit mode (protocol between tasks)

1. `object.mode_set(mode, toggle)` (§2.7.3) validates `mode` against the dynamic enum
   `object_modes_for(active)` — `POSE` on a mesh -> `PropertyTypeError` with `'enum "POSE" not found
   in ('OBJECT', 'EDIT', 'SCULPT', 'VERTEX_PAINT', 'WEIGHT_PAINT', 'TEXTURE_PAINT')'` **[O]** — and
   calls `Object.q_set_mode(mode)` on the active object and on the selected objects of the same type **[I]**; `toggle=True`
   on an object already in that mode returns to `OBJECT` **[O]**.
2. `Object.q_set_mode` (§2.2.6) stores the mode and, when entering or leaving `"EDIT"`, calls
   `data.q_set_editmode(True/False)` if the data has that method.
3. `Mesh.q_set_editmode` (§2.3.1): `True` -> `is_editmode = True` **[O]** and `enter(mesh)` hook;
   `False` -> `flush(mesh)` hook if `q_edit_data` is not `None`, `q_edit_data = None`,
   `is_editmode = False`, stamps `"GEOMETRY"`.
4. `quartz.bmesh` (§3.3.1) installs `flush` (writes to `mesh.q_geometry` the BMesh held in
   `q_edit_data`); `bmesh.from_edit_mesh(mesh)` creates and stores that BMesh on the first call.
5. `context.mode == "EDIT_MESH"` when editing a mesh **[O]**; `edit_object` and `objects_in_mode`
   per §2.6.2 **[O]**.
6. `Object.update_from_editmode()` -> `data.q_flush_edit()` (writes without leaving the mode).

### 2.2 IDs, scene and depsgraph (`l2-idmodel`)

Modules: `quartz.types` (package), `quartz.types.naming`, `quartz.types.id`, `quartz.types.blenddata`,
`quartz.types.object`, `quartz.types.collection`, `quartz.types.scene`, `quartz.types.world`,
`quartz.types.wm`, `quartz.depsgraph`. Uses only L1 (§0.6); never imports `quartz.registry`,
`quartz.session`, `quartz.contexts` or modules of `l2-datablocks`, except for the `importlib` load
in `load_builtin_types()` (§2.0.1, rule 1; §2.2.1, rule 1) (the context arrives through the
`hooks.current_context()` hook, registered names through `resolve_name`, object data through duck
typing, §2.2.6, rule 12).

Internal import graph (module level; the reverse only inside functions):
`naming` <- `id` <- `blenddata` <- `collection` <- `object` <- `world` <- `quartz.depsgraph` <- `scene` <-
`wm`. `quartz/types/__init__.py` imports at module level only stdlib, numpy, `quartz.rna`,
`quartz.math` and `quartz.app.msgbus`; none of these imports installs hooks.

Rules common to all modules in this section:

1. Every new RNA type is `@builtin_struct` with `_q_strict_attrs = True` (§2.0.3, 2). Each module
   in this section defines `__all__` with the RNA classes, the collections and the public functions/constants of
   its signature block (`_q_…` names stay out). Classes with a
   pointer to their own class (`Object.parent`) annotate the prop as a string and apply the decorator
   **after** the body (`Object = builtin_struct(Object)`), so that §1.6.6 evaluates the annotation with the
   name already bound; an annotation that fails silently is a defect (the tests check
   `"parent" in Object.bl_rna.properties`).
2. Declared RNA props use the name, type, subtype, unit, size, default, limits and items from the dump
   (`id_types`/`sub_structs`, §2.4). Computed props use `meta={"virtual_get", "virtual_set"}`.
   Pointers to **non-ID** structs that need to be writable (`ViewLayer.active_layer_collection`,
   `Window.view_layer`) are Python properties, because §1.6.4 treats writes to these pointers as
   read-only. Virtual pointers to IDs declared here (`Scene.collection`,
   `Object.active_material`, `MaterialSlot.material`, `Depsgraph.scene*`, `DepsgraphUpdate.id`,
   `DepsgraphObjectInstance.object`) carry `meta["counts_user"] = False` and never generate an `IDRef`
   (§2.2.4, rule 3); `ID.original` (self-reference) is a Python property.
3. Derived collections (`Scene.objects`, `Scene.view_layers`, `Collection.objects/children`,
   `Object.modifiers`, `WindowManager.windows`, …) are Python properties that return a
   `PropCollection` cached per instance (stable identity); they do not appear in
   `bl_rna.properties` and are not compared by §2.4. Persistent derived elements (view layers,
   modifiers, vertex groups, material slots, windows, keymaps) are created once and
   stored (stable identity, §2.0.3, 1) and receive `_q_set_owner(owner, path)` (§1.6.7), so
   that `id_data`, `path_from_id()` and `repr` work.
4. Errors: only classes from `quartz.errors`; messages that cite `bpy.data` use
   `settings.api_prefix`; the missing-symbols log uses the Blender name (§2.0.3).

#### 2.2.1 `quartz/types/__init__.py`

```python
BUILTIN_TYPE_MODULES: tuple[str, ...] = (
    "quartz.types.id", "quartz.types.blenddata", "quartz.types.object", "quartz.types.collection",
    "quartz.types.scene", "quartz.types.world", "quartz.types.wm", "quartz.depsgraph",         # l2-idmodel
    "quartz.types.mesh", "quartz.types.material", "quartz.types.camera", "quartz.types.light",
    "quartz.types.image", "quartz.types.text",                                                  # l2-datablocks
    "quartz.types.operator", "quartz.types.ui", "quartz.types.prefs", "quartz.types.stubs",
    "quartz.ui",                                                                                 # l2-registry-ui
    "quartz.contexts",                                                                           # l2-runtime
)
RNA_REEXPORTS: tuple[str, ...] = ("PropertyGroup", "PropCollection", "PropArray")
def load_builtin_types() -> tuple[str, ...]  # modules loaded so far, in the order of BUILTIN_TYPE_MODULES
def install_hooks() -> None                  # hooks.install(wrap_array=wrap_array, on_property_changed=on_property_changed)
def wrap_array(values: np.ndarray, pdef: PropertyDef, inst: object, on_write: Callable[[], None]) -> object
def on_property_changed(inst: object, pdef: PropertyDef) -> None   # quartz.app.msgbus.notify_changed(inst, pdef.identifier)
def set_name_resolver(fn: Callable[[str], type | None] | None) -> None
def resolve_name(name: str) -> type | None
def __getattr__(name: str) -> object
def __dir__() -> list[str]
```

1. `load_builtin_types()`: for each module not yet loaded, `importlib.import_module`;
   a `ModuleNotFoundError` whose `.name` is the module itself (or a parent of it) -> skip, and it is tried again
   on the next call; any other error (including a `ModuleNotFoundError` for a different name) propagates.
   Idempotent; returns the tuple of loaded modules.
2. Catalog: for each loaded module, each name in `__all__` whose object is a class with `"bl_rna"`
   in its **own** `__dict__` or a subclass of `quartz.rna.PropCollection`; plus the three objects in
   `RNA_REEXPORTS` (those from `quartz.rna`). Rebuilt when the set of loaded modules
   grows. A name present in two modules -> `RegistrationError` with `"duplicate RNA name"` (the
   modules cited in the message). Each module in `BUILTIN_TYPE_MODULES` MUST define `__all__`.
3. `__getattr__(name)`: `name` starting with `"_"` -> immediate `AttributeError` (the import machinery
   and `inspect` probe dunders; nothing is loaded); otherwise, in this order: current catalog (on the
   first lookup in the process, after `load_builtin_types()`); if not found,
   `load_builtin_types()` again (it only tries the modules still missing) and the rebuilt catalog if it
   grew; then `resolve_name(name)`; otherwise
   `AttributeError(f"module 'quartz.types' has no attribute '{name}'")`. Nothing is stored
   as a package attribute (repeated lookups return the same object from the owning module).
4. `__dir__()` -> `sorted(catalog ∪ RNA_REEXPORTS)` (loads the modules).
5. `wrap_array` (only for `pdef.kind == "FLOAT"`; other types -> `PropArray`):

| Subtype | Condition | Result |
|---|---|---|
| `TRANSLATION`, `DIRECTION`, `VELOCITY`, `ACCELERATION`, `XYZ`, `XYZ_LENGTH`, `COORDINATES` | 1D, size 2–4 | `Vector._q_wrap(values, owner=inst, on_write=on_write)` |
| `EULER` | 1D, size 3 | `Euler._q_wrap(..., order=pdef.meta["euler_order"](inst))` if the key exists, otherwise `"XYZ"` |
| `QUATERNION` | 1D, size 4 | `Quaternion._q_wrap(...)` |
| `COLOR`, `COLOR_GAMMA` | 1D, size 3 | `Color._q_wrap(...)` (size 4 -> `PropArray` **[O]** `Object.color`) |
| `MATRIX` | 2D | `Matrix._q_wrap(values, ...)`; array row `i` = `Matrix` row `i`, without transposing **[I]** |
| any other (includes `AXISANGLE`, `NONE`, INT, BOOLEAN), or a listed subtype with the condition false (e.g. `bound_box` 8×3) | — | `PropArray(values, on_write=on_write, owner=inst, pdef=pdef)` |

   Each read returns a new wrapper (`ob.location is ob.location` is false **[O]** judge
   `object.defaults`).
6. `set_name_resolver(fn)` stores `fn` (`None` disables it); `resolve_name(name)` -> `fn(name)` or
   `None`. Installed by `quartz.session.install_hooks()` with `quartz.registry.lookup`.
7. `import quartz.types` MUST NOT install hooks or import submodules.

Errors: `RegistrationError` (`"duplicate RNA name"`); `AttributeError` (`"module 'quartz.types' has
no attribute"`).

#### 2.2.2 `quartz/types/naming.py`

```python
MAX_NAME_BYTES: int = 255
RENAME_MODES: tuple[str, ...] = ("NEVER", "ALWAYS", "SAME_ROOT")                               # [O] dump ID.rename
RENAME_RESULTS: tuple[str, ...] = ("UNCHANGED", "UNCHANGED_COLLISION", "RENAMED_NO_COLLISION",
                                   "RENAMED_COLLISION_ADJUSTED", "RENAMED_COLLISION_FORCED")    # [O]
def truncate_utf8(name: str, max_bytes: int = MAX_NAME_BYTES) -> str
def split_suffix(name: str) -> tuple[str, int | None]
def unique_name(name: str, taken: Callable[[str], bool], *, default: str) -> str
def sort_key(name: str) -> str
def plan_rename(current: str, requested: str, taken: Callable[[str], bool], *, mode: str = "NEVER",
                default: str) -> tuple[str, str, str | None]
    # (result, new name of the one being renamed, new name of the other ID or None); pure function
```

1. `truncate_utf8`: the longest prefix whose UTF-8 encoding has ≤ `max_bytes` bytes, cutting at a
   character boundary: 300 × `"N"` -> 255 characters; 200 × `"Ã"` -> 127 characters = 254 bytes
   **[O]** (dump `id_semantics`).
2. `split_suffix`: if the name ends with `"."` + one or more ASCII digits and the preceding part is not
   empty -> `(base, int(digits))`; otherwise `(name, None)` (`"Cube.001"` -> `("Cube", 1)`, `"Cube.1"` ->
   `("Cube", 1)`, `"Cube."` -> `("Cube.", None)`, `".001"` -> `(".001", None)`) **[I]**.
3. `unique_name`: empty -> `default` **[O]** (`"Mesh"`); truncates; free -> returns it. Taken -> `base =
   split_suffix(name)[0]`; for `n = 1, 2, …` the candidate `f"{base}.{n:03d}"` (with `base` truncated
   so that the candidate fits in 255 bytes) — returns the first free one **[O]** (`QProbe`,
   `QProbe.001`, `QProbe.002`).
4. `sort_key(name) == name.casefold()`. ID collections insert with `bisect_right` on this key
   (after the equal ones), which gives the observed stable order `_x, a, A, a10, a2, b, B, Zed` for
   the creation order `b, B, a, A, a10, a2, Zed, _x` **[O]** (judge `id.order`), with no "natural" sorting.
5. `plan_rename` (`taken` does NOT consider `current`):
   1. `mode ∉ RENAME_MODES` -> `PropertyTypeError` with `f'enum "{mode}" not found in ('`.
   2. `target = truncate_utf8(requested) or default`.
   3. `target == current` -> `("UNCHANGED", current, None)`.
   4. `not taken(target)` -> `("RENAMED_NO_COLLISION", target, None)` **[O]**.
   5. Collision and (`mode == "ALWAYS"` or (`mode == "SAME_ROOT"` and `split_suffix(current)[0] ==
      split_suffix(target)[0]` **[I]**)) -> `("RENAMED_COLLISION_FORCED", target, other)` with `other =
      unique_name(target, lambda n: taken(n) or n == target, default=default)`: the one being renamed gets
      the exact name and the other ID gets the suffix **[O]** (judge `id.rename`: `["QZRN.001", "QZRN"]`).
   6. Otherwise: `new = unique_name(target, taken, default=default)`; `new == current` ->
      `("UNCHANGED_COLLISION", current, None)` **[I]** (dump: renaming `QProbe.001` to `QProbe`
      with `QProbe` taken leaves `QProbe.001` **[O]**); otherwise `("RENAMED_COLLISION_ADJUSTED", new,
      None)` **[O]**.

#### 2.2.3 Dirty channels and global clock

Defined in `quartz/types/id.py`. This is the definition cited by §1.6.1 (`meta["dirty"]`).

```python
DIRTY_CHANNELS: tuple[str, ...] = ("DATA", "TRANSFORM", "GEOMETRY", "SHADING", "SELECT", "HIERARCHY", "VISIBILITY")
def dirty_clock() -> int        # current value; starts at 0; process-global; never decreases and is never reset
def dirty_tick() -> int         # increments by 1 and returns the new value
# in ID:
q_dirty: Mapping[str, int]                          # ro; read-only view: channel -> stamp (0 = never); the 7 channels are always present
def q_tag(self, *channels: str) -> None             # no arguments = ("DATA",)
def q_dirty_since(self, stamp: int) -> frozenset[str]   # channels with stamp > stamp
def _q_on_change(self, pdef: PropertyDef) -> None   # self.q_tag(pdef.meta.get("dirty", "DATA"))
```

1. `q_tag` validates all channels first (outside `DIRTY_CHANNELS` -> `PropertyValueError` with
   `"unknown dirty channel"`), calls `dirty_tick()` **once** and writes that stamp to each requested
   channel. On a removed ID, the tombstone raises `RemovedStructError` first (§2.2.4). Storage: the
   internal dictionary `_q_stamps: dict[str, int]` (created in `_q_construct` with the 7 channels at 0);
   `q_dirty` is a Python property that returns `types.MappingProxyType(self._q_stamps)`. The
   stamps are NOT part of `_q_state_get`/`_q_state_set` or of the `.qz`, and `ID.copy()` does not
   copy them (the new ID gets its own, rule 6).
2. A write through a `PropertyDef` on an ID stamps `meta.get("dirty", "DATA")` (step 6 of §1.6.4). On a nested
   struct, `Struct._q_on_change` delegates to `id_data._q_on_change(pdef)` (§1.6.7), so the
   channel is the one from the `meta` of the struct's prop and the stamp goes to the owning ID. The embedded master collection
   stamps itself (it is an ID).
3. `Object._q_on_change` extends: identifier `"parent"` -> `q_tag("HIERARCHY", "TRANSFORM")`.
4. `_q_state_set`, `write_raw` and construction (`_q_construct`) do NOT stamp; `quartz.io.state.apply`
   stamps (§2.1.5).
5. Channel per built-in prop (props not listed: `"DATA"`):

| Type | Props | Channel |
|---|---|---|
| `Object` | `location`, `rotation_*`, `scale`, `delta_*`, `matrix_basis/local/world`, `matrix_parent_inverse`, `parent_type`, `dimensions` | `TRANSFORM` |
| `Object` | `parent` | `HIERARCHY` (+ `TRANSFORM`, rule 3) |
| `Object` | `data` | `GEOMETRY` **[I]** |
| `Object` | `hide_viewport`, `hide_render`, `hide_select` | `VISIBILITY` |
| `Object` | `color`, `active_material`, `active_material_index`, `display_type` | `SHADING` **[I]** |
| `Object` | `instance_type`, `instance_collection` | `HIERARCHY` **[I]** |
| `Modifier` (owner: object) | all | `GEOMETRY` **[I]** |
| `Collection` | `hide_viewport`, `hide_render`, `hide_select` | `VISIBILITY` |
| `Scene` | `world` | `SHADING` **[I]** |
| `World` | all | `SHADING` **[I]** |
| `ViewLayer` (owner: scene) | `use` | `VISIBILITY` |
| `LayerCollection` (owner: scene) | `exclude`, `hide_viewport`, `holdout`, `indirect_only` | `VISIBILITY` |

6. Structural mutations (no descriptor) stamp explicitly:

| Mutation | Stamped ID | Channels |
|---|---|---|
| `CollectionObjects.link/unlink` | the collection (the master stamps itself) and the object | `HIERARCHY` |
| `CollectionChildren.link/unlink` | the parent collection and the child | `HIERARCHY` |
| `Object.select_set`, `LayerObjects.active = …` | the object; for `active`, also the scene | `SELECT` |
| `Object.hide_set` | the object | `VISIBILITY` |
| `Object.q_set_mode` | the object | `DATA` |
| `ObjectModifiers.new/remove/clear/move` | the object | `GEOMETRY` **[I]** |
| `VertexGroups.new/remove/clear`, `VertexGroup.add/remove` | the object | `DATA` |
| `ViewLayers.new/remove/move` | the scene | `HIERARCHY` |
| `ID.rename` (and the other ID in a `FORCED`) | the renamed ID(s) | `DATA` |
| `IDCollection.new`, `ID.copy`, `BlendDataObjects.new` | the new ID | all 7 channels |
| `IDCollection.remove` | collections that lost links (§2.1.4, 3.5); `dirty_tick()` always | `HIERARCHY` |
| `ID.update_tag(refresh)` | itself | `DATA` (+ `TRANSFORM` if `"OBJECT" in refresh`) |

   `Scene.frame_set` does NOT stamp (it writes `frame_current`/`frame_subframe` with `write_raw`, §2.2.8,
   rule 6), like Blender, which clears the recalculation marks when changing frames.

7. Depsgraph (§2.2.11): `TRANSFORM` -> `is_updated_transform`, `GEOMETRY` -> `is_updated_geometry`,
   `SHADING` -> `is_updated_shading`; any channel puts the ID in `updates`.

#### 2.2.4 `quartz/types/id.py`

```python
@builtin_struct(identifier="ID")
class ID(Struct):
    _q_strict_attrs = True; _q_is_id = True
    _q_removed: ClassVar[bool] = False
    q_id_type: ClassVar[str] = ""
    q_schema_version: ClassVar[int] = 1
    # rna (dump id_types["ID"]):
    name: StringProperty(maxlen=256, meta={"virtual_get", "virtual_set"})   # get: _q_name; set: self.rename(v, mode="NEVER")
    name_full: StringProperty(maxlen=516, ro virt)       # == _q_name
    id_type: EnumProperty(items=<39 items from the dump>, default="ACTION", ro virt)   # == q_id_type
    session_uid: IntProperty(soft_min=-10000, soft_max=10000, ro virt)   # process-global counter, starting at 1 [I], never reused
    users: IntProperty(subtype="UNSIGNED", ro virt)      # _q_main.q_users_of(self) + int(use_fake_user); without _q_main: int(use_fake_user)
    use_fake_user: BoolProperty(); use_extra_user: BoolProperty(); tag: BoolProperty()
    is_evaluated, is_embedded_data, is_missing, is_runtime_data, is_editable, is_linked_packed, is_library_indirect: BoolProperty(ro virt)
        # False, except is_editable (True [I]) and is_embedded_data (True only on the master collection)
    # Python properties (not PropertyDef):
    original: "ID"                                       # self
    library = library_weak_reference = asset_data = override_library = preview = None   # read-only
    def __new__(cls, *args, **kwargs) -> NoReturn        # TypeError: IDs are born through collections or _q_construct [I]
    def rename(self, name: str, *, mode: str = "NEVER") -> str
    def copy(self) -> "ID"
    def evaluated_get(self, depsgraph: "Depsgraph") -> "ID"          # self
    def user_clear(self) -> None
    def user_remap(self, new_id: "ID") -> None
    def user_of_id(self, id: "ID") -> int
    def make_local(self, *, clear_proxy: bool = True, clear_liboverride: bool = False, clear_asset_data: bool = True) -> "ID"   # self
    def update_tag(self, *, refresh: set[str] = frozenset()) -> None
    def animation_data_create(self) -> NoReturn; def animation_data_clear(self) -> None
    def asset_mark(self) -> NoReturn; def asset_clear(self) -> NoReturn; def asset_generate_preview(self) -> NoReturn
    def preview_ensure(self) -> NoReturn; def override_create(self, *a, **k) -> NoReturn; def override_hierarchy_create(self, *a, **k) -> NoReturn
    def __repr__(self) -> str
    # dirty channels: §2.2.3
    # ---- internal protocol ----
    _q_main: "BlendData | None"                          # None outside bpy.data; on the master, reflects the scene's
    _q_name: str; _q_stamps: dict[str, int]              # storage for the name and the stamps (§2.2.3)
    @classmethod
    def _q_construct(cls, name: str) -> "ID"
    def _q_copy_into(self, new: "ID") -> None
    def _q_refs(self) -> Iterator[IDRef]
    def _q_state_get(self) -> dict
    def _q_state_set(self, state: dict) -> None
    def _q_tombstone(self) -> None
    @staticmethod
    def _q_revive(obj: "ID") -> None
    @classmethod
    def q_upgrade(cls, state: dict, from_version: int) -> dict

@dataclass(frozen=True)
class IDTypeInfo:
    cls: type[ID]; id_type: str; collection: str; default_name: str; collection_cls: "type[IDCollection] | None"
def register_id_type(cls: type[ID], *, id_type: str, collection: str, default_name: str,
                     collection_cls: "type[IDCollection] | None" = None) -> None
def id_type_info(key: type | str) -> IDTypeInfo | None
def iter_id_types() -> Iterator[IDTypeInfo]
def removed_class_for(cls: type[ID]) -> type
def _q_registry_snapshot() -> object                 # internal, for tests only: copy of the type registry
def _q_registry_restore(snap: object) -> None
```

1. **Construction**: `_q_construct(name)` creates the instance through `Struct.__new__(cls)` (bypassing
   `ID.__new__`), assigns `session_uid`, writes the name to `_q_name` **without** checking uniqueness (already
   final; only `truncate_utf8`), `_q_main = None`, zeroed `_q_stamps` and the type's members. The name
   lives only in `_q_name`: the `virtual_get` of `name`/`name_full` returns it. Subclasses extend (`super()._q_construct(name)` and
   then initialize their own members; `Mesh` creates the geometry). Instantiating `ID`/a subclass directly ->
   `TypeError` with `"can not be created directly"` **[I]**.
2. **Name** (`name` and `rename`): delegates to `plan_rename` with `taken = name used by another ID of the same
   collection`, `default = info.default_name`; applies the names (the other ID first, in a `FORCED`),
   reorders the collection (`sort_key`, insertion after the equal ones: renaming `QZR_c` to `QZR_0` moves it to
   before `QZR_a` **[O]** judge `id.order_after_rename`), stamps `DATA` and returns the result.
   Temporary ID (`_q_main` `None`): only truncates; result `"UNCHANGED"`/`"RENAMED_NO_COLLISION"`.
   Embedded ID (`is_embedded_data`, the master collection, whose `_q_main` reflects the scene's):
   the name stays `"Scene Collection"` and the result is `"UNCHANGED"` **[I]**. Non-`str` `name` ->
   `PropertyTypeError` from §1.6.4.
3. **Users and references** (normative table in §2.1.4): `ID._q_refs` does NOT call
   `Struct._q_refs`; it reimplements the generic one from §1.6.7 with a single difference — it skips every
   `PointerDef` with `meta["virtual_get"]` (computed pointers are never references: `clear` on them
   would fail, and `users` cannot depend on them). That is: for each **stored** ID `PointerDef`
   with `read_raw(self)` not `None`, an `IDRef(target, owner=self, kind="POINTER", counts_user=
   pdef.counts_user, on_remove=pdef.on_remove, clear=<pdef.write_raw(self, None) and then
   self._q_on_change(pdef)>, remap=<same with the new target>)`; for pointers to a PropertyGroup and items of a
   `CollectionProperty`, `yield from item._q_refs()`. The types in this task extend it
   (§2.2.6–2.2.10); when the generic one already emits the reference for a built-in prop, the type only
   relabels the `kind` with `ref._replace(kind=...)` on the first `IDRef` whose `owner is self` and
   `target is` the prop's value (`Object.data` -> `"DATA"`, `Scene.world` -> `"WORLD"`) —
   `counts_user`/`on_remove` come from the prop's `meta`. `users` is never stored.
4. **`copy()`**: temporary ID (`_q_main` `None`) or embedded (`is_embedded_data`) ->
   `NotImplementedInQuartz("ID.copy")` **[I]**; `WindowManager`/`Screen`/`WorkSpace` -> same **[I]**.
   Otherwise `new = type(self)._q_construct(unique_name(self.name, taken, default=info.default_name))`
   (`taken` = name used in the ID's collection), `self._q_copy_into(new)`, `_q_link` into the same collection of
   `bpy.data` (without scene collections), stamps the 7 channels and returns; 0 users **[O]**
   (`QProbe.002`, `copy_users` 0). Default `_q_copy_into`: `s = self._q_state_get()`, removes
   `"name"`, `new._q_state_set(s)` (references to IDs remain the same instances: `Object.copy()`
   shares `data`; nested PGs are copied).
5. `user_clear()`: `ref.clear()` for each `IDRef` in `_q_main.q_refs_to(self)` and `use_fake_user =
   False` (Blender only zeroes the counter and leaves the references dangling; Quartz undoes them to
   keep the derived `users` coherent **[I]**); without `_q_main`, only `use_fake_user = False`. `user_remap(new_id)`: non-ID `new_id` -> `PropertyTypeError`; different `q_id_type` ->
   `PropertyValueError` with `"same type"` **[I]**; `new_id is self` -> nothing; otherwise `ref.remap(new_id)`
   on each reference. `user_of_id(id)`: number of `IDRef` in `self._q_refs()` with `target is id`
   (counting all, whether `counts_user` or not).
6. `update_tag(refresh)`: items outside `{"OBJECT", "DATA", "TIME"}` -> `PropertyTypeError` (enum message,
   §1.6.4); stamps from §2.2.3.
7. NI: `animation_data_create` -> `NotImplementedInQuartz("ID.animation_data_create")`; likewise
   `asset_mark`, `asset_clear`, `asset_generate_preview`, `preview_ensure`, `override_create`,
   `override_hierarchy_create` (symbol `f"ID.{name}"`); `animation_data_clear` is a no-op.
8. **`repr`**: `f"{hooks.repr_root()}.data.{info.collection}['{name}']"` (`"bpy.data.objects['QZD']"`
   with compat **[O]**); master collection: `f"{repr(scene)}.collection"` **[O]**
   (`"bpy.data.scenes['Scene'].collection"`); ID without `_q_main` and not embedded:
   `f'<bpy_struct, {T}("{name}") at 0x{id(self):016X}>'` **[I]**.
9. **Removal and tombstone** (§2.1.4, items 3–4): `_q_tombstone()` does `self.__class__ =
   removed_class_for(type(self))` (idempotent). `removed_class_for(cls)` creates once per class and
   caches a subclass of `cls` with `__name__ = cls.__name__`, `_q_removed = True` and
   `_q_live_class = cls`, outside any `__all__`; non-dunder `__getattribute__`/`__setattr__`/`__delattr__`
   raise `RemovedStructError(f"StructRNA of type {cls.bl_rna.identifier} has
   been removed")` **[O]** (`"…of type Mesh has been removed"`); `repr` ->
   `f"<bpy_struct, {cls.bl_rna.identifier} invalid>"` **[I]**; `hash`/`==` remain by
   identity. `ID._q_revive(obj)`: if `type(obj)._q_removed`, `obj.__class__ =
   type(obj)._q_live_class`; otherwise no-op.
10. **State** (§2.1.5): `_q_state_get()` = `super()._q_state_get()` + `{"name"}` (the flags
    `use_fake_user`/`use_extra_user`/`tag` are stored props and travel in `"p"`/`"set"`);
    `_q_state_set` writes the raw `_q_name` (no `plan_rename`, no uniqueness
    check: whoever applies state guarantees unique names, §2.6) and then the rest; if the ID is
    linked and the name changed, it is repositioned in its collection by the insertion rule of §2.2.2 (4).
    `session_uid`, `_q_main` and `_q_stamps` are not part of the state. Default `q_upgrade` returns
    `state`.
11. `register_id_type`: writes `cls.q_id_type = id_type`; same class with the same data -> no-op;
    `id_type` outside the items of the `ID.id_type` enum -> `RegistrationError` with `"unknown id_type"`;
    `id_type` or `collection` already used by **another** class -> `RegistrationError` with `"already
    registered"`. `id_type_info(key)`: class -> first registered class in the MRO; `str` -> by
    `id_type` (`"MESH"`) and then by `collection` (`"meshes"`); nothing -> `None`. `iter_id_types()`
    in registration order. `_q_registry_snapshot/_q_registry_restore` exist only for tests that
    register fake types.

Errors: `RemovedStructError` (`"has been removed"`); `RegistrationError` (`"already registered"`,
`"unknown id_type"`); `PropertyTypeError` (`'enum "'`, `"not found in ("`); `PropertyValueError`
(`"same type"`, `"unknown dirty channel"`); `NotImplementedInQuartz` (`"ID.animation_data_create"`,
`"ID.copy"`, `"is not implemented in Quartz"`); `TypeError` (`"can not be created directly"`).

#### 2.2.5 `quartz/types/blenddata.py`

```python
COLLECTION_NAMES: Mapping[str, str]   # 40 entries, dump order (below)
IMPLEMENTED: frozenset[str]           # objects meshes materials cameras lights collections scenes worlds images texts
                                      # window_managers screens workspaces
class IDCollection(PropCollection):
    q_info: IDTypeInfo
    def __init__(self, main: "BlendData", info: IDTypeInfo) -> None
    def new(self, name: str) -> ID
    def remove(self, id: ID, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None
    def tag(self, value: bool) -> None
    def _q_link(self, id: ID) -> None
    def _q_unlink(self, id: ID) -> None
class PhantomIDCollection(PropCollection):
    def __init__(self, main: "BlendData", attr: str) -> None
    def new(self, *args, **kwargs) -> NoReturn; def remove(self, *args, **kwargs) -> NoReturn; def load(self, *args, **kwargs) -> NoReturn
    def tag(self, value: bool) -> None
@builtin_struct(identifier="BlendData")
class BlendData(Struct):
    filepath: StringProperty(subtype="FILE_PATH", maxlen=1024, ro virt)
    is_dirty: BoolProperty(ro virt); is_saved: BoolProperty(ro virt)       # dirty_clock() > _q_clean_stamp; filepath != ""
    use_autopack: BoolProperty()
    version: IntVectorProperty(subtype="XYZ", size=3, min=0, meta={"readonly": True})
        # stored (not virtual), dump default (0, 0, 0); written only with write_raw; read as PropArray
    # + the 40 COLLECTION_NAMES attributes as Python properties (stable instances)
    def __init__(self) -> None
    def batch_remove(self, ids: Iterable[ID]) -> None
    def orphans_purge(self, do_local_ids: bool = True, do_linked_ids: bool = True, do_recursive: bool = False) -> int
    def user_map(self, subset: Iterable[ID] | None = None, key_types: set[str] | None = None,
                 value_types: set[str] | None = None) -> dict[ID, set[ID]]
    def temp_data(self, filepath: str | None = None) -> NoReturn
    def file_path_map(self, *a, **k) -> NoReturn; def file_path_foreach(self, *a, **k) -> NoReturn
    def pack_linked_ids_hierarchy(self, root_id: ID) -> NoReturn
    # native
    def q_iter_ids(self, *, include_embedded: bool = False) -> Iterator[ID]
    def q_collection_for(self, key: ID | type | str) -> IDCollection | None
    def q_refs_to(self, id: ID) -> list[IDRef]
    def q_users_of(self, id: ID) -> int
    def q_clear(self, *, keep: Iterable[ID] = ()) -> None
    def q_set_filepath(self, path: str) -> None
    def q_mark_clean(self) -> None
    def q_set_version(self, version: tuple[int, int, int] | None) -> None    # write_raw; None -> quartz.app.version
```

`COLLECTION_NAMES` (attribute → RNA name, dump order **[O]**): `cameras` BlendDataCameras,
`scenes` BlendDataScenes, `objects` BlendDataObjects, `materials` BlendDataMaterials, `node_groups`
BlendDataNodeTrees, `meshes` BlendDataMeshes, `lights` BlendDataLights, `libraries`
BlendDataLibraries, `screens` BlendDataScreens, `window_managers` BlendDataWindowManagers, `images`
BlendDataImages, `lattices` BlendDataLattices, `curves` BlendDataCurves, `metaballs`
BlendDataMetaBalls, `fonts` BlendDataFonts, `textures` BlendDataTextures, `brushes`
BlendDataBrushes, `worlds` BlendDataWorlds, `collections` BlendDataCollections, `shape_keys`
BlendDataShapeKeys **[I]**, `texts` BlendDataTexts, `speakers` BlendDataSpeakers, `sounds`
BlendDataSounds, `armatures` BlendDataArmatures, `actions` BlendDataActions, `particles`
BlendDataParticles, `palettes` BlendDataPalettes, `annotations` BlendDataAnnotations,
`grease_pencils` BlendDataGreasePencilsV3, `movieclips` BlendDataMovieClips, `masks`
BlendDataMasks, `linestyles` BlendDataLineStyles, `cache_files` BlendDataCacheFiles,
`paint_curves` BlendDataPaintCurves, `workspaces` BlendDataWorkSpaces, `lightprobes`
BlendDataProbes, `hair_curves` BlendDataHairCurves, `pointclouds` BlendDataPointClouds, `volumes`
BlendDataVolumes, `all_ids` IDs **[I]**.

1. `BlendData()` works without a session: `quartz.types.load_builtin_types()`; for each attribute of
   `COLLECTION_NAMES`: a type registered with that `collection` → `(info.collection_cls or
   IDCollection)(self, info)`; `all_ids` → read-only view (internal class) over
   `q_iter_ids()`, without `new`/`remove`; all others → `PhantomIDCollection(self, attr)`. A missing
   type attribute (sibling does not exist yet, e.g. `meshes` before `l2-datablocks`) is a phantom: only
   `IMPLEMENTED` is the gate's target. `filepath = ""` **[O]**; `_q_clean_stamp = dirty_clock()` (so
   `is_dirty` is false until the next stamp of any ID in the process); `version` written with
   `write_raw(tuple(quartz.app.version))`. `l2-runtime` MAY rewrite `version` with `write_raw` or
   `q_set_version` (the two forms are equivalent).
2. Reading a phantom attribute calls `hooks.note_missing(f"bpy.data.{attr}")`; `new`/`remove`/`load`
   → `NotImplementedInQuartz(f"{P}.data.{attr}.new")` (`.remove`, `.load`) — including on collections
   that in Blender lack one of these methods (benign divergence **[I]**); `tag` is a no-op; `len` is 0;
   `repr` → `f"<bpy_collection[0], {COLLECTION_NAMES[attr]}>"`. `all_ids` iterates in the order of
   `q_iter_ids()` (Blender uses the internal type order — `images`, `materials`, …; divergence
   **[I]**).
3. `IDCollection`: items in stable `sort_key` order (§2.2.2); `_q_key` = `name`; MAY
   override `get`/`find`/`__getitem__`/`__contains__` with a name index, keeping the
   messages of §1.6.5 (`KeyError` with `'bpy_prop_collection[key]: key "__nope__" not found'`
   **[O]**). `repr(data.objects) == "<bpy_collection[3], BlendDataObjects>"` **[O]** (class
   name). `new(name)` (base): non-`str` `name` → `PropertyTypeError`; `info.cls._q_construct(
   unique_name(name, taken, default=info.default_name))`, `_q_link`, stamps the 7 channels. `_q_link`
   inserts at the sorted position and sets `id._q_main = main` (no stamp and no handlers); `_q_unlink`
   removes without a tombstone and without undoing references. `tag(value)` writes `tag` on all items.
4. `remove(id, …)`: sequence of §2.1.4, item 3 (tombstone first raises `RemovedStructError`
   **[O]**; `do_unlink=False` with `users > 0` → `LinkError` with `"must have zero users to be
   removed"` **[I]**; `DELETE_OWNER` cascading **[O]**; `ref.clear()` on the rest; children of the removed
   object are left with `parent = None` without compensating the matrix **[I]**; collections that lost links
   stamp `HIERARCHY`; `dirty_tick()`). Removing a `Scene` also tombstones its master
   collection (the `IDRef`s whose owner is the master vanish with it). An argument that is not an instance of
   `info.cls` → `PropertyTypeError` with `f"expected a {info.cls.bl_rna.identifier} type"` **[I]**;
   an instance of the right type that is not in this collection (temporary, embedded or from another
   `BlendData`) → `LinkError` with `"not in"` **[I]**. `do_id_user`/`do_ui_user` are accepted and ignored. The
   collections of this task redefine `remove` with the dump name as the 1st parameter and delegate
   positionally to the base (`objects.remove(object=ob)`); `l2-datablocks` does the same in its own.
5. `q_iter_ids(include_embedded)`: collections from `IMPLEMENTED` that are present, in the order of
   `COLLECTION_NAMES`, each in its own order; `include_embedded=True` puts the master collection right
   after each scene. `q_refs_to(id)` walks `q_iter_ids()` **without** embedded IDs and collects the `IDRef`s
   with `target is id` (references of the master collection arrive through the scene's `_q_refs`, `owner` = the
   master). `q_users_of(id)` = sum of `counts_user` over that set.
6. `batch_remove(ids)`: ID already removed on entry → `RemovedStructError`; computes the closure by
   `DELETE_OWNER`, undoes the references from outside the set and tombstones all of them (no
   observable order). `orphans_purge`: removes (without cascade, like `batch_remove`) the IDs with `users == 0`,
   except `SCENE`, `WINDOWMANAGER`, `SCREEN`, `WORKSPACE` and embedded ones **[I]**; `do_recursive` repeats until none remain; `do_local_ids=False`
   → 0; returns how many it removed **[O]** (integer). `user_map`: for each key (all IDs from
   `q_iter_ids()` or `subset`, filtered by `key_types` = set of `id_type`), the set of
   IDs that reference it (owner of an `IDRef`; embedded owner or nested struct → the owning ID via
   `id_data`/scene), filtered by `value_types`; keys without users are present with `set()` **[O]**
   format (`{Cube(mesh): {Cube(object)}}`).
7. `q_clear(keep)`: without handlers or cascade, in this order: (1) `R` = IDs from `q_iter_ids()` that are not
   in `keep` (by identity); each one leaves its collection (`_q_unlink`, `_q_main = None`); (2) for
   each kept ID, `ref.clear()` on each `IDRef` of its `_q_refs()` whose target is in `R` (so
   a window of the kept WM ends up with `scene = None`, since no other scene remains); (3) tombstone on each
   ID of `R` and on the master of each scene of `R`. `q_set_filepath(path)` stores the path (`str(path)`); `q_mark_clean()` does
   `_q_clean_stamp = dirty_clock()`. NI: `temp_data`, `file_path_map`, `file_path_foreach`,
   `pack_linked_ids_hierarchy` (symbol `f"BlendData.{name}"`).

Errors: `NotImplementedInQuartz` (`f"{P}.data.actions.new"`); `LinkError` (`"must have zero users to
be removed"`, `"not in"`); `RemovedStructError` (`"has been removed"`); `KeyError` (`"not found"`);
`PropertyTypeError` (`"expected a"`).

#### 2.2.6 `quartz/types/object.py`

```python
OBJECT_TYPES: tuple[str, ...]      # the 16 items of Object.type, dump order [O]
OBJECT_MODES: tuple[str, ...]      # the 14 items of Object.mode [O]
EULER_ORDERS: tuple[str, ...]      # is quartz.math.euler.EULER_ORDERS
MODIFIER_TYPES: tuple[str, ...]    # the 83 items of Modifier.type, dump order [O]
def register_object_data_type(cls: type[ID], object_type: str) -> None
def object_type_for(data: ID | None) -> str
def object_modes_for(ob: "Object") -> tuple[str, ...]
def context_mode_for(ob: "Object | None") -> str
class Object(ID):                  # decorated after the body (rule 1 at the top)
    # rna (data from dump id_types["Object"]; channels in §2.2.3), at minimum: data, type (virt ro), mode (virt ro), parent,
    # parent_type, matrix_parent_inverse, location, rotation_mode, rotation_euler (meta euler_order), rotation_quaternion,
    # rotation_axis_angle, scale, delta_location, delta_rotation_euler, delta_rotation_quaternion, delta_scale,
    # lock_location, lock_rotation, lock_rotation_w, lock_rotations_4d, lock_scale, matrix_basis/matrix_local/matrix_world
    # (virt rw), dimensions (virt rw), bound_box (virt ro), hide_viewport, hide_render, hide_select, display_type,
    # show_name, show_axis, show_wire, show_in_front, show_bounds, color, pass_index, empty_display_type,
    # empty_display_size, instance_type, instance_collection (type=Collection), active_material (virt), active_material_index
    # Python properties (derived collections, rule 3 at the top):
    children: tuple["Object", ...]; children_recursive: list["Object"]
    users_collection: tuple["Collection", ...]; users_scene: tuple["Scene", ...]
    material_slots: PropCollection; modifiers: "ObjectModifiers"; constraints: "ObjectConstraints"; vertex_groups: "VertexGroups"
    animation_data: None
    def select_get(self, view_layer: "ViewLayer | None" = None) -> bool
    def select_set(self, state: bool, view_layer: "ViewLayer | None" = None) -> None
    def hide_get(self, view_layer: "ViewLayer | None" = None) -> bool
    def hide_set(self, state: bool, view_layer: "ViewLayer | None" = None) -> None
    def visible_get(self, view_layer: "ViewLayer | None" = None, viewport: object = None) -> bool
    def holdout_get(self, view_layer=None) -> bool; def indirect_only_get(self, view_layer=None) -> bool   # False
    def to_mesh(self, preserve_all_data_layers: bool = False, depsgraph: "Depsgraph | None" = None) -> ID
    def to_mesh_clear(self) -> None
    def convert_space(self, pose_bone: object = None, matrix: Matrix | None = None, from_space: str = "WORLD", to_space: str = "WORLD") -> Matrix
    def update_from_editmode(self) -> bool
    def ray_cast(self, origin, direction, distance: float = 1.70141e+38, depsgraph=None) -> tuple[bool, Vector, Vector, int]
    def closest_point_on_mesh(self, origin, distance: float = 1.84467e+19, depsgraph=None) -> tuple[bool, Vector, Vector, int]
    def is_modified(self, scene, settings: str) -> bool; def is_deform_modified(self, scene, settings: str) -> bool   # False
    def find_armature(self) -> None; def cache_release(self) -> None
    # remaining dump functions (shape_key_add/remove/clear, shape_keys_selected, local_view_get/set, visible_in_viewport_get,
    # calc_matrix_camera, camera_fit_coords, crazyspace_*, to_curve, to_curve_clear) -> NotImplementedInQuartz(f"Object.{name}")
    def q_set_mode(self, mode: str) -> None
class ObjectModifiers(PropCollection):
    active: "Modifier | None"      # rw
    def new(self, name: str, type: str) -> "Modifier"; def remove(self, modifier: "Modifier") -> None
    def clear(self) -> None; def move(self, from_index: int, to_index: int) -> None
@builtin_struct
class Modifier(Struct):            # props from dump sub_structs["Modifier"] (name, type ro, show_*, is_active, use_pin_to_last, persistent_uid ro, …)
class ObjectConstraints(PropCollection):
    active: None
    def new(self, type: str) -> NoReturn; def remove(self, constraint: object) -> None; def clear(self) -> None
    def move(self, from_index: int, to_index: int) -> None; def copy(self, constraint: object) -> NoReturn
class VertexGroups(PropCollection):
    active: "VertexGroup | None"; active_index: int                  # rw
    def new(self, name: str = "Group") -> "VertexGroup"; def remove(self, group: "VertexGroup") -> None; def clear(self) -> None
@builtin_struct
class VertexGroup(Struct):         # name (rw, unique per object), index (ro), lock_weight
    def add(self, index: Sequence[int], weight: float, type: str) -> None    # "REPLACE" | "ADD" | "SUBTRACT"
    def remove(self, index: Sequence[int]) -> None
    def weight(self, index: int) -> float
@builtin_struct
class MaterialSlot(Struct):        # link ("DATA"), material (virt), slot_index (ro), name (ro)
class BlendDataObjects(IDCollection):
    def new(self, name: str, object_data: ID | None) -> Object
    def remove(self, object: Object, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None
# end of module: register_id_type(Object, id_type="OBJECT", collection="objects", default_name="Object", collection_cls=BlendDataObjects)
```

1. **Object data**: `register_object_data_type(cls, t)`: `t ∉ OBJECT_TYPES` or `t == "EMPTY"` →
   `RegistrationError` with `"invalid object type"`; same class and type → no-op; a different class for
   `t`, or the same class with a different type → `RegistrationError` with `"already registered"`.
   `object_type_for(None) == "EMPTY"` **[O]**; otherwise the type of the first registered class in the MRO;
   not registered → `PropertyTypeError` with `"can not be used as object data"` **[I]**. Internal state
   with `_q_registry_snapshot/_q_registry_restore` (tests only), as in §2.2.4.
2. `data`: `PointerProperty(type=ID, poll=…, meta={"on_remove": "DELETE_OWNER", "counts_user": True,
   "dirty": "GEOMETRY"})`, stored (not virtual). Poll: an object whose `data` is `None` (Empty) rejects
   any ID; otherwise it accepts only `object_type_for(v) == self.type` (failure → `PropertyValueError` of
   §1.6.4) **[I]** — Blender silently ignores it. The poll returns true for `None`:
   `ob.data = None` is accepted and the object becomes `EMPTY` **[I]** (Blender ignores it). `type` is virtual read-only (`object_type_for(data)`;
   writing → `ReadOnlyError` with `'bpy_struct: attribute "type" from "Object" is read-only'`
   **[O]**). `_q_refs`: generic, with the `kind` of the `data` ref relabeled to `"DATA"` (§2.2.4,
   3); `parent` (`counts_user=False`) and `instance_collection` (`counts_user=True`) stay `"POINTER"`.
   `BlendDataObjects.new(name, object_data)`: `object_type_for(object_data)` (error above), constructs,
   writes `data` with `write_raw`, links, stamps; does not link into a collection (0 users **[O]**).
3. **Defaults** **[O]** (judge `object.defaults`): `rotation_quaternion (1,0,0,0)`,
   `rotation_axis_angle (0,0,1,0)`, `rotation_mode "XYZ"`, `empty_display_type "PLAIN_AXES"`,
   `empty_display_size 1.0`, `display_type "TEXTURED"`, `dimensions (0,0,0)` without data, `color
   (1,1,1,1)`. Messages **[O]**: `rotation_mode = "NOPE"` → `PropertyTypeError` with `'enum "NOPE"
   not found in (\'QUATERNION\', \'XYZ\', \'XZY\', \'YXZ\', \'YZX\', \'ZXY\', \'ZYX\',
   \'AXIS_ANGLE\')'`; `location = (1, 2)` → `PropertyValueError` with `"sequences of dimension 0
   should contain 3 items, not 2"`; unknown attribute → `AttributeError("'Object' object has no
   attribute 'qz_unknown_attr'")`.
4. **Transforms** (computations in float64, result float32; `R(·)` = 3×3 matrix):
   - `t = location + delta_location`; `s = scale ⊙ delta_scale`.
   - Euler (`rotation_mode` ∈ `EULER_ORDERS`): `R_total = R(Euler(delta_rotation_euler, order)) ·
     R(Euler(rotation_euler, order))`; `QUATERNION`: `R(q_delta ⊗ normalize(q))` (zero quaternion
     → identity); `AXIS_ANGLE`: `R(Euler(delta_rotation_euler, "XYZ")) · R(normalized axis,
     angle)` (zero axis → identity) **[I]**.
   - `matrix_basis = T(t) · R_total · S(s)`; `matrix_local = matrix_parent_inverse · matrix_basis`;
     `matrix_world = parent.matrix_world · matrix_local` (no parent: `matrix_local`), computed on
     every read (D9; Blender only updates after `view_layer.update()` **[O]**, divergence 3 of
     ARCHITECTURE §13). A `parent_type` other than `OBJECT` is stored and ignored **[I]**.
   - `rotation_euler`/`delta_rotation_euler` use `meta["euler_order"] = lambda ob: ob.rotation_mode
     if ob.rotation_mode in EULER_ORDERS else "XYZ"` **[O]** (`QUATERNION` → `"XYZ"`, `ZYX` →
     `"ZYX"`).
   - Writing to `matrix_world` → `matrix_local = inv(parent.matrix_world) · M`; to `matrix_local` →
     `matrix_basis = inv(matrix_parent_inverse) · M` (singular: pseudo-inverse); to `matrix_basis`:
     decomposes immediately **[O]** (`matrix_world = Translation((5,0,0))` → `location == (5,0,0)`):
     `location = translation − delta_location`; scale = norms of the columns of the 3×3, all three negated
     if the determinant is negative **[I]**, divided by `delta_scale` (component 0 → keeps the current value);
     rotation = normalized columns without the delta, converted to the current mode (Euler with
     `euler_compat` = current value; axis-angle via the quaternion). The components (`location`,
     `rotation_*`, `scale`) are written without callbacks or msgbus (like `write_raw`), updating in
     place the arrays already stored in `_p` so that live wrappers see the new value; the write of the
     matrix itself follows §1.6.4 (stamps `TRANSFORM` once, notifies the matrix identifier).
   - `parent = p` does not recompute `matrix_parent_inverse` (it stays identity **[O]**), so the child
     "jumps": child at `(5,0,0)` under a parent at `(10,0,0)` → `matrix_world.translation == (15,0,0)`
     (in Blender only after `view_layer.update()` **[O]**; in Quartz already on the next read, D9).
     Poll of `parent`: rejects `self` and descendants (`PropertyValueError`) **[I]**.
   - `dimensions` (virt): `(max − min)` of `data.q_bounds()` multiplied component by component
     by the magnitude of the scale of `matrix_world`; without data or without `q_bounds` → zeros **[O]**. Write:
     for each axis with extent > 0, `scale[i] = copysign(value[i] / extent[i], scale[i])`
     **[I]**. `bound_box` (virt, ro, 8×3): corners of `(min, max)` in the order of §1.5.5; without data →
     zeros.
5. **Selection and visibility** (live in the `ViewLayer` bases): resolves the view layer: argument; otherwise
   `getattr(hooks.current_context(), "view_layer", None)`; otherwise the 1st view layer of the 1st scene (order
   of `_q_main.scenes`) whose view layer objects contain `self`; otherwise none. `select_get` /
   `hide_get`: base of the view layer (`ViewLayer.q_base`) or `False` (object outside → `False` **[O]**
   judge `object.select_get_unlinked`). `select_set`/`hide_set`: no view layer or object outside →
   `LinkError` with `"not in View Layer"` **[I]**; writes to the base and stamps (§2.2.3).
   `visible_get`: in the view layer, base not hidden, `hide_viewport` false and some visible
   `LayerCollection` that contains the object **[I]**.
6. **Derived** (scans, never stored): `children` = objects of `_q_main.objects` with
   `parent is self`, in collection order (no `_q_main` → `()`); `children_recursive` in pre-order
   **[I]**; `users_collection` = collections of `bpy.data.collections` that contain it (collection order)
   and then the master collections of the scenes that link it directly (scene order) **[I]**; `users_scene` =
   scenes of `_q_main.scenes` (in collection order) whose tree contains it.
7. **Materials**: `material_slots` has one item per element of `data.materials` (without `data` or without
   `materials` → empty); the `MaterialSlot`s are stored by index on the object (the same index
   returns the same object while it exists; the list grows/shrinks with `len(data.materials)` on every
   access), `_q_path = f"material_slots[{i}]"`, `slot_index = i`, `name` = name of the material or `""`.
   `MaterialSlot.material` and `Object.active_material` (= slot `active_material_index`) are
   virtual pointers (`type=ID`, `fixed_type_name="Material"`, `counts_user=False`); writing a
   non-material → `PropertyTypeError` with `"expected a Material type"` (tested by
   `bl_rna.identifier == "Material"` in the MRO, without importing `l2-datablocks`); the write replaces only the
   slot: if `i < len(data.materials)`, `data.materials[i] = m`; otherwise (no slots)
   `data.materials.append(m)` **[I]**. The write MUST NOT call `data.materials.clear()` (on the real
   `Mesh`, `clear` deletes the `material_index` attribute and would reset the per-face material assignment,
   §2.3.1, rule 17). `link = "OBJECT"` → `NotImplementedInQuartz("MaterialSlot.link")`.
8. **Modes**: `object_modes_for(ob)` by `ob.type`: `MESH` → `("OBJECT", "EDIT", "SCULPT",
   "VERTEX_PAINT", "WEIGHT_PAINT", "TEXTURE_PAINT")` **[O]**; `CURVE`, `SURFACE`, `FONT`, `META`,
   `LATTICE` → `("OBJECT", "EDIT")` **[I]**; `ARMATURE` → `("OBJECT", "EDIT", "POSE")` **[I]**;
   all others (including `EMPTY`) → `("OBJECT",)` **[I]**. `context_mode_for`: `None` or mode `OBJECT` →
   `"OBJECT"`; `EDIT` → `EDIT_MESH` (MESH **[O]**), `EDIT_CURVE`, `EDIT_SURFACE`, `EDIT_TEXT`
   (FONT), `EDIT_METABALL`, `EDIT_LATTICE`, `EDIT_ARMATURE`, `EDIT_CURVES`, `EDIT_POINTCLOUD`,
   `EDIT_GREASE_PENCIL` **[I]**; `POSE` → `"POSE"`; `SCULPT` → `"SCULPT"`; `VERTEX_PAINT` →
   `"PAINT_VERTEX"`; `WEIGHT_PAINT` → `"PAINT_WEIGHT"`; `TEXTURE_PAINT` → `"PAINT_TEXTURE"`;
   `PARTICLE_EDIT` → `"PARTICLE"`; all others → the mode itself **[I]**. `mode` is virtual read-only.
   `q_set_mode(mode)`: `mode ∉ object_modes_for(self)` → `PropertyValueError` with
   `f'mode "{mode}" not supported'` **[I]**; same mode → nothing; when entering or leaving `EDIT`,
   calls `data.q_set_editmode(True/False)` if it exists (before writing the exit, after writing the
   entry) **[I]**; stamps `DATA`. `update_from_editmode()`: `mode == "EDIT"` and `data` with
   `q_flush_edit` → `data.q_flush_edit()`; otherwise `False`.
9. **Modifiers** (data only, no evaluation): `new(name, type)`: `type ∉ MODIFIER_TYPES` →
   `PropertyTypeError` (enum message); unique name on the object (`unique_name`); plain `Modifier`
   instance (Blender returns the subclass of the type: divergence **[I]**) with
   `show_viewport/show_render/show_in_editmode/show_expanded = True` **[I]**, `type` written with
   `write_raw` (read-only) and `persistent_uid` = per-object counter starting at 1 **[I]**;
   `_q_path = f'modifiers["{name}"]'`; the new one becomes `active`. Renaming a modifier applies
   `unique_name` among the names of the others on the same object and updates `_q_path` **[I]**. `move`
   out of range → `IndexError`. `remove` of a foreign modifier → `LinkError` with
   `"not in object"` **[I]**. `ObjectConstraints`: always empty; `new`/`copy` →
   `NotImplementedInQuartz("ObjectConstraints.new"/".copy")`; `remove` → `LinkError`. `VertexGroups`:
   `index` = position; weights in a per-group dictionary (outside the mesh) **[I]**; `weight(i)` of an
   absent vertex → `LinkError` with `"not in group"` **[I]**; invalid `type` in `add` → `PropertyTypeError`.
10. `to_mesh()`: `type == "MESH"` → `new = type(data)._q_construct(data.name)`,
    `data._q_copy_into(new)`, outside `bpy.data`, stored in `_q_temp_mesh` (the previous one is
    discarded); other types → `NotImplementedInQuartz("Object.to_mesh")` **[I]**.
    `to_mesh_clear()` discards (`_q_tombstone`). `convert_space`: `matrix` `None` → identity;
    spaces `WORLD`, `LOCAL_WITH_PARENT` (`inv(P) · M`), `LOCAL` (`inv(P · matrix_parent_inverse) ·
    M`) and inverses, with `P = parent.matrix_world` (no parent: identity) **[I]**; `POSE` →
    `NotImplementedInQuartz("Object.convert_space")`; unknown name → `PropertyTypeError` **[I]**.
    `ray_cast`/`closest_point_on_mesh`: in object space, over `data.q_geometry` (duck typing)
    triangulated with `quartz.geometry.triangulate` (corners → vertices via `corner_verts`) and queried
    through `quartz.math.bvhtree.BVHTree._q_from_triangles`; `index` = polygon; no hit →
    `(False, Vector((0,0,0)), Vector((0,0,0)), -1)`; without `q_geometry` → the same tuple (Blender
    raises `RuntimeError` for an object without a mesh) **[I]**.
11. **State**: own keys `"mode"`, `"modifiers"` (list of the `_q_state_get()` of each
    modifier, with `"type"`), `"vertex_groups"` (list of `{"name", "lock_weight", "indices":
    ndarray int32, "weights": ndarray float32}`); `_q_state_set` writes the raw mode (without edit
    hooks). `_q_copy_into` copies modifiers and groups, shares `data` and resets the mode to
    `OBJECT`.
12. **Object data protocol** (duck typing; implemented by `l2-datablocks` and by the fake data of the tests; each
    member is optional and checked with `getattr`/`hasattr`):
    `data.q_bounds() -> tuple[np.ndarray, np.ndarray]` (local bounds; absent → zeros);
    `data.q_set_editmode(state: bool) -> None`; `data.q_flush_edit() -> bool`; `data.materials`
    (sequence of `Material | None` with `__setitem__(i, m)`, `append(m)` and `clear()`); `data.q_geometry`
    (`quartz.geometry.MeshGeometry`, for `ray_cast`, `statistics` and `Scene.ray_cast`).

Errors: `RegistrationError` (`"invalid object type"`, `"already registered"`); `PropertyTypeError`
(`"can not be used as object data"`, `'enum "NOPE" not found in ('`, `"expected a Material type"`);
`PropertyValueError` (`"should contain 3 items, not 2"`, `"not supported"`); `ReadOnlyError`
(`'attribute "type" from "Object" is read-only'`); `LinkError` (`"not in View Layer"`, `"not in
object"`, `"not in group"`); `NotImplementedInQuartz` (`"Object.shape_key_add"`).

#### 2.2.7 `quartz/types/collection.py`

```python
@builtin_struct
class Collection(ID):
    # rna (dump): hide_select, hide_viewport, hide_render, color_tag (default "COLOR_01"), instance_offset
    objects: "CollectionObjects"; children: "CollectionChildren"; all_objects: tuple["Object", ...]   # Python properties
    children_recursive: list["Collection"]; users_dupli_group: tuple["Object", ...]
class CollectionObjects(PropCollection):
    def link(self, object: "Object") -> None; def unlink(self, object: "Object") -> None
class CollectionChildren(PropCollection):
    def link(self, child: Collection) -> None; def unlink(self, child: Collection) -> None
class BlendDataCollections(IDCollection):
    def new(self, name: str) -> Collection
    def remove(self, collection: Collection, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None
# end of module: register_id_type(Collection, id_type="COLLECTION", collection="collections", default_name="Collection",
#                                collection_cls=BlendDataCollections)
```

1. `objects`/`children` iterate in **link order** **[O]**; key = name. `link(object)`:
   non-`Object` -> `PropertyTypeError` with `"expected a Object type"`; duplicate ->
   `LinkError(f"Object '{o.name}' already in collection '{c.name}'")` **[O]** (master:
   `'Scene Collection'`); appends at the end and stamps. `unlink` of an absent object -> `LinkError` with `"not in
   collection"` **[I]**.
2. `children.link(child)`: non-`Collection` -> `PropertyTypeError`; embedded child (master) ->
   `LinkError` with `"embedded"` **[I]**; duplicate -> `LinkError` with `"already in collection"`
   **[I]**; `child is self` or an ancestor -> `LinkError` with `"cycle"` **[I]**.
3. `all_objects` = objects of the collection and its descendants, pre-order (objects in link order,
   then children in link order), without repetition; `children_recursive` in pre-order;
   `users_dupli_group` = objects of `_q_main.objects` with `instance_collection is self`.
4. `_q_refs` = generic + `IDRef(target=ob, owner=self, kind="COLLECTION_OBJECT", counts_user=True,
   on_remove="CLEAR", ...)` per object and `kind="COLLECTION_CHILD"` per child (§2.1.4); `clear`
   unlinks without error and stamps `HIERARCHY`; `remap` swaps in place (if the new one is already linked, it only
   removes the old one) **[I]**. New collection: 0 users; linked to a scene: 1 **[O]**.
5. **Master collection** (created by `Scene._q_construct`): `Collection._q_construct("Scene
   Collection")` **[O]** with `_q_embedded_owner = scene`; `is_embedded_data` true; outside
   `bpy.data.collections`; its `_q_main` is a descriptor that reflects the scene's `_q_main`; `repr`
   §2.2.4, item 8; fixed name (§2.2.4, item 2); `copy()` -> NI (§2.2.4, item 4); `remove` through
   `data.collections` -> `LinkError` (§2.2.5, item 4); goes to the tombstone together with the scene.
6. **State**: own keys `"objects"` and `"children"` (lists of instances in link order).
   `_q_copy_into` copies the links (shallow copy).

Errors: `LinkError` (`"already in collection"`, `"not in collection"`, `"cycle"`, `"embedded"`);
`PropertyTypeError` (`"expected a Object type"`).

#### 2.2.8 `quartz/types/scene.py`

```python
@builtin_struct
class RenderSettings(Struct):   # engine, resolution_x, resolution_y, resolution_percentage, fps, fps_base, filepath, film_transparent
                                # (defaults do dump: "BLENDER_EEVEE", 1920, 1080, 100, 24, 1.0, "//", False)
@builtin_struct
class UnitSettings(Struct):     # system ("NONE"), system_rotation, scale_length (default 1.0 [I]), use_separate, length_unit, mass_unit, time_unit, temperature_unit
@builtin_struct
class ToolSettings(Struct):     # mesh_select_mode, use_proportional_edit, proportional_size, transform_pivot_point, use_snap, use_keyframe_insert_auto
@builtin_struct
class View3DCursor(Struct):     # location, rotation_mode, rotation_euler (euler_order), rotation_quaternion, rotation_axis_angle, matrix (virt, rw)
@builtin_struct
class LayerCollection(Struct):  # collection (virt ro), name (virt ro), exclude/holdout/indirect_only/hide_viewport (virt rw), is_visible (virt ro)
    children: "PropCollection"  # Python property
    def visible_get(self) -> bool; def has_objects(self) -> bool; def has_selected_objects(self, view_layer: "ViewLayer") -> bool
class LayerObjects(PropCollection):
    active: "Object | None"; selected: tuple["Object", ...]
@builtin_struct
class ViewLayer(Struct):
    # rna: name (maxlen 64, virt rw), use, layer_collection (virt ro), depsgraph (virt ro, HIDDEN)
    objects: LayerObjects; active_layer_collection: LayerCollection     # Python properties (the 2nd is rw)
    def update(self) -> None                                            # depsgraph_for(scene, self).update()
    def update_render_passes(self) -> None                              # no-op
    def q_base(self, ob: "Object") -> tuple[bool, bool] | None          # internal to the task
class ViewLayers(PropCollection):
    def new(self, name: str) -> ViewLayer; def remove(self, layer: ViewLayer) -> None; def move(self, from_index: int, to_index: int) -> None
class SceneObjects(PropCollection): ...
class TimelineMarkers(PropCollection):       # always empty
    def new(self, name: str, frame: int = 1) -> NoReturn; def remove(self, marker: object) -> NoReturn; def clear(self) -> None
@builtin_struct
class Scene(ID):
    # rna: camera (counts_user False), world, collection (virt ro, counts_user False), frame_current, frame_start, frame_end, frame_step,
    # frame_float (virt), frame_subframe, frame_current_final (virt ro), use_preview_range, frame_preview_start, frame_preview_end,
    # render, unit_settings, tool_settings, cursor (ro pointers to the structs above), gravity, use_gravity, use_nodes
    objects: SceneObjects; view_layers: ViewLayers; timeline_markers: TimelineMarkers; animation_data: None   # Python properties
    def frame_set(self, frame: int, subframe: float = 0.0) -> None
    def statistics(self, view_layer: ViewLayer) -> str
    def ray_cast(self, depsgraph, origin, direction, distance: float = 1.70141e+38) -> tuple[bool, Vector, Vector, int, "Object | None", Matrix]
    def update_render_engine(self) -> None
    def sequence_editor_create(self) -> NoReturn; def sequence_editor_clear(self) -> NoReturn; def uvedit_aspect(self, object) -> NoReturn
class BlendDataScenes(IDCollection):
    def new(self, name: str) -> Scene
    def remove(self, scene: Scene, do_unlink: bool = True) -> None
# end of module: register_id_type(Scene, id_type="SCENE", collection="scenes", default_name="Scene", collection_cls=BlendDataScenes)
```

1. `Scene._q_construct(name)`: master collection (§2.2.7, 5) and a view layer `"ViewLayer"` **[I]**
   (the factory name is `"ViewLayer"` **[O]**); `render`/`unit_settings`/`tool_settings`/`cursor`
   are `PointerProperty` to the embedded structs (lazy instance from §1.6.4; `repr`
   `"bpy.data.scenes['Scene'].render"`). The factory values (METRIC, scale 1.0, ...) are written
   by `build_factory_scene` (§2.6.1), not here.
2. **Tree and objects**: `Scene.objects` = objects of the master's tree in pre-order (objects in
   link order, then children), without repetition, ignoring `exclude` **[O]** (factory `Cube, Light,
   Camera`). `ViewLayer.objects` = same order, skipping collections with `exclude` in that view layer
   (an object also linked to an included collection appears) **[O]**.
3. **LayerCollection**: one per collection path starting at the master, cached by (view layer,
   path) for stable identity; `name` = collection name; the four flags `exclude/
   hide_viewport/holdout/indirect_only` are virtual props whose storage is a dictionary of the
   view layer indexed by collection (one entry per collection, even with several paths **[I]**;
   default `False`); `exclude` on the master is ignored **[I]**; `is_visible` = no `exclude`, no `hide_viewport`, `collection.hide_viewport`
   false and parent visible **[I]**; `visible_get() == is_visible`; `has_objects()` = there are linked
   objects; `has_selected_objects(vl)` = any of them with `select_get(vl)`. `active_layer_collection`
   (default: the root **[I]**) rejects a layer outside the tree with `PropertyValueError` **[I]**.
4. **Bases**: the view layer keeps `{object: [select, hide]}`, created on demand with
   `(False, False)`; `q_base(ob)` -> tuple, or `None` (and discards the entry) if `ob` is not in the
   view layer's objects **[I]**. `LayerObjects.active`: object outside -> `PropertyValueError` with
   `"not in View Layer"` **[I]**; `selected` = objects with a selected base, in the order of the objects.
5. `ViewLayers.new(name)`: name unique in the scene (`unique_name`, default `"ViewLayer"`) **[I]**, empty
   bases, root active; `remove(layer)`: last one -> `LinkError` with `"at least one"`, foreign ->
   `LinkError` with `"not in scene"` **[I]**; renaming (`name`) keeps uniqueness and updates
   `_q_path` (`'view_layers["ViewLayer"]'`).
6. `frame_set(frame, subframe=0.0)` (probe of the dump `undo_and_handlers.handler_log`), in this order:
   1. `frame` must be `int` (`bool` accepted as 0/1; `float` -> `PropertyTypeError` with
      `"expected an int"` **[I]**); clamps `frame` to `[-1048574, 1048574]` and `subframe` to
      `[0, 1]`; writes `frame_current` and `frame_subframe` with `write_raw` (no stamp, no msgbus,
      no `update`);
   2. `vl` = `ctx.view_layer` if `ctx = hooks.current_context()` is not `None`, `ctx.scene is self`
      and that view layer belongs to this scene; otherwise `self.view_layers[0]`; `dg = depsgraph_for(self, vl)`;
   3. `handlers.dispatch("frame_change_pre", self, dg)` — `frame_current` is already the new one **[O]** (7);
      Blender delivers `depsgraph` `None` in this handler **[O]**, but Quartz passes `dg` because
      §1.2.2/§2.1.2 fix `(scene, depsgraph)` (benign divergence; callbacks must accept
      `*args` or `depsgraph=None`; recorded in `DIVERGENCES` of
      `tests/contract/test_contract_undo_handlers.py`, §3.1.8);
   4. `dg.update()` (§2.2.11: only dispatches `depsgraph_update_pre/post` if some reachable ID changed
      since the last `update`; Blender does not dispatch them on a frame change **[O]** — probe
      `handler_log`: no `depsgraph_update_*` between `frame_change_pre` and `frame_change_post`);
   5. `handlers.dispatch("frame_change_post", self, dg)` (2 arguments `Scene`, `Depsgraph` **[O]**).
   `frame_set` stamps nothing (§2.2.3): hence, in the probe sequence — `frame_set(7)`,
   `view_layer.update()`, `ob.location.x += 0.0`, `view_layer.update()`, `frame_set(1)` — the log is
   exactly `pre(7), post, depsgraph_update_post, pre(1), post` **[O]** (the only
   `depsgraph_update_post` comes from the second `update()`, triggered by the write to `location`).
   `frame_float` (virt) = `frame_current + frame_subframe`; write: `floor` -> `frame_current`,
   fraction -> `frame_subframe` **[I]**; `frame_current_final` the same, read-only.
7. `statistics(vl)` **[I]** = `f"{vl.name} | Objects:{sel}/{total}"` + `f" | Verts:{v} | Faces:{f}"`
   when some object has `data.q_geometry`. `Scene.ray_cast`: over `depsgraph.objects` with
   `q_geometry`, in world space; returns the nearest hit; no hit -> `(False, zeros,
   zeros, -1, None, Matrix.Identity(4))` **[I]**. `update_render_engine` no-op; NI:
   `sequence_editor_create`, `sequence_editor_clear`, `uvedit_aspect` (`f"Scene.{name}"`).
8. `View3DCursor.matrix` (virt): `T(location) · R(mode)` with the same mode rule as the object; write
   decomposes into `location`/rotation.
9. **Users and references**: `Scene._q_refs` = generic (`camera` `POINTER` not countable **[O]**,
   `world` relabeled `"WORLD"` countable **[O]**, `collection` not countable) + `yield from
   self.collection._q_refs()` (links of the master). `scenes.remove`: last scene -> `LinkError` with
   `"last"` **[I]**; windows that showed it follow the `WINDOW_SCENE` rule (§2.2.10); objects linked
   only to it become orphans.
10. **State**: own keys `"collection"` (state of the master: the dict from its `_q_state_get()`,
    never the instance) and `"view_layers"` (list of `{"name", "p" (struct generic), "bases":
    [[ob, select, hide], …], "active": ob | None, "flags": [[collection | None, exclude,
    hide_viewport, holdout, indirect_only], …], "active_path": [collection, …]}`). The master never
    appears as an instance in the state (the `.qz` rejects embedded IDs, §2.6): in `"flags"` it is
    `None`, and `"active_path"` lists only the collections below the master (`[]` = the root). Bases of objects
    that are no longer in the view layer are omitted. `_q_state_set` reuses `ViewLayer` by position
    (identity), creates the missing ones and discards the extras **[I]**. `_q_state_set` calls
    `ID._q_revive(master)` before restoring the master through the key `"collection"` (undoing the removal
    of a scene revives the scene through `quartz.io.state.apply` and the master here; no-op if alive).
    `_q_copy_into` copies props, view layers (bases included) and the master's links (shallow copy)
    **[I]**.

Errors: `PropertyTypeError` (`"expected an int"`); `PropertyValueError` (`"not in View Layer"`);
`LinkError` (`"at least one"`, `"not in scene"`, `"last"`); `NotImplementedInQuartz`.

#### 2.2.9 `quartz/types/world.py`

```python
@builtin_struct
class WorldLighting(Struct):     # use_ambient_occlusion (False), ao_factor (1.0), distance (10.0) [I]
@builtin_struct
class WorldMistSettings(Struct): # use_mist (False), intensity (0.0), start (5.0), depth (25.0), height (0.0), falloff ("QUADRATIC") [I]
@builtin_struct
class World(ID):                 # rna: color (COLOR 3, default 0.05 [O dump]; read as Color), use_nodes, light_settings, mist_settings (ro)
    node_tree: None; animation_data: None                       # Python properties
class BlendDataWorlds(IDCollection):
    def new(self, name: str) -> World
    def remove(self, world: World, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None
# end of module: register_id_type(World, id_type="WORLD", collection="worlds", default_name="World", collection_cls=BlendDataWorlds)
```

A new `World` has 0 users; `scene.world = w` -> 1 **[O]** (judge `id.users.world_after_scene`).
All props of `World`, `WorldLighting` and `WorldMistSettings` carry `meta["dirty"] = "SHADING"`
(those of the sub-structs reach the `World` through the delegation of §1.6.7). `light_settings`/`mist_settings`
are read-only `PointerProperty` to the sub-structs (lazy instance from §1.6.4); the two
sub-structs do not exist in the dump (`sub_structs`), so their fields are **[I]** and §2.4 does not
compare them. State: generic only.

#### 2.2.10 `quartz/types/wm.py`

```python
EVENT_TYPES: tuple[str, ...]      # the 196 items of KeyMapItem.type, dump order [O] (also those of key_modifier)
@builtin_struct
class Screen(ID):                 # is_temporary (ro False); areas (Python, empty)
@builtin_struct
class WorkSpace(ID):              # object_mode (items of OBJECT_MODES, "OBJECT"); tools (Python, empty)
@builtin_struct
class Timer(Struct):              # time_step, time_delta (0.0), time_duration (0.0) — ro
@builtin_struct
class Window(Struct):             # rna: scene (PointerProperty(type=Scene), stored), screen (PointerProperty(type=Screen),
                                  # stored, ro), workspace (PointerProperty(type=WorkSpace), stored), x, y, width, height (ro)
                                  # — screen/workspace with counts_user False; all written with write_raw when ro
    view_layer: "ViewLayer | None"  # Python property rw
class Windows(PropCollection):
    def find_playing(self, scrub: bool = False) -> None             # always None (nothing plays) [I]
@builtin_struct
class KeyMapItem(Struct):         # props of the dump sub_structs["KeyMapItem"] except properties/propvalue (type/key_modifier with EVENT_TYPES)
    properties: object | None     # Python property (ro)
    propvalue: str                # Python property rw ("NONE" default; dynamic items in Blender)
    def compare(self, item: "KeyMapItem") -> bool                   # same idname, type, value, any, shift, ctrl, alt, oskey,
                                                                    # hyper, key_modifier, direction, repeat, propvalue [I]
    def to_string(self, compact: bool = False) -> NoReturn          # NI("KeyMapItem.to_string")
@builtin_struct
class KeyMap(Struct):             # name, space_type, region_type, is_modal (ro, written with write_raw); bl_owner_id
    keymap_items: "KeyMapItems"
    def active(self) -> "KeyMap"                                    # self [I]
    def restore_to_default(self) -> None                            # no-op
    def restore_item_to_default(self, item: "KeyMapItem") -> None   # no-op
class KeyMapItems(PropCollection):
    def new(self, idname: str, type: str, value: str, any: bool = False, shift: int = 0, ctrl: int = 0, alt: int = 0, oskey: int = 0,
            hyper: int = 0, key_modifier: str = "NONE", direction: str = "ANY", repeat: bool = False, head: bool = False) -> KeyMapItem
    def new_modal(self, propvalue: str, type: str, value: str, any: bool = False, shift: int = 0, ctrl: int = 0, alt: int = 0,
                  oskey: int = 0, hyper: int = 0, key_modifier: str = "NONE", direction: str = "ANY", repeat: bool = False) -> KeyMapItem
    def new_from_item(self, item: KeyMapItem, head: bool = False) -> KeyMapItem   # copy of the fields, new id
    def remove(self, item: KeyMapItem) -> None; def from_id(self, id: int) -> KeyMapItem | None
    def find_from_operator(self, idname: str, properties: object = None, include: set[str] = frozenset(),
                           exclude: set[str] = frozenset()) -> KeyMapItem | None   # 1st item with that idname [I]
    def find_match(self, *a, **k) -> NoReturn; def match_event(self, *a, **k) -> NoReturn   # NI(f"KeyMapItems.{name}")
class KeyMaps(PropCollection):
    def new(self, name: str, space_type: str = "EMPTY", region_type: str = "WINDOW", modal: bool = False, tool: bool = False) -> KeyMap
    def find(self, name: str, space_type: str = "EMPTY", region_type: str = "WINDOW") -> KeyMap | None
    def remove(self, keymap: KeyMap) -> None
@builtin_struct
class KeyConfig(Struct):          # name
    keymaps: KeyMaps
class KeyConfigurations(PropCollection):
    addon: KeyConfig; user: KeyConfig; default: KeyConfig; active: KeyConfig      # ro
    def new(self, name: str) -> KeyConfig; def remove(self, keyconfig: KeyConfig) -> None
    def update(self, keep_properties: bool = False) -> None                        # no-op
    def find_item_from_operator(self, idname: str, context: str = "INVOKE_DEFAULT", properties: object = None,
                                include: set[str] = frozenset(), exclude: set[str] = frozenset()
                                ) -> tuple["KeyMap | None", "KeyMapItem | None"]  # 1st pair (keymap, item) with that idname in active [I]
@builtin_struct
class WindowManager(ID):
    windows: Windows; keyconfigs: KeyConfigurations; operators: PropCollection   # Python properties
    clipboard: str                                                                # Python property (python member in the dump [O])
    # headless methods (names and parameters of the dump sub_structs["WindowManager"]["functions"]):
    def modal_handler_add(self, operator: object) -> bool
    def fileselect_add(self, operator: object) -> None
    def event_timer_add(self, time_step: float, window: "Window | None" = None) -> "Timer"
    def event_timer_remove(self, timer: "Timer") -> None
    def progress_begin(self, min: float, max: float) -> None
    def progress_update(self, value: float) -> None
    def progress_end(self) -> None
    def invoke_props_dialog(self, operator: object, width: int = 300, title: str = "", confirm_text: str = "",
                            cancel_default: bool = False, text_ctxt: str = "", translate: bool = True) -> set[str]
    def invoke_props_popup(self, operator: object, event: object) -> set[str]
    def invoke_popup(self, operator: object, width: int = 300, *, auto_keymap: bool = True) -> set[str]
    def invoke_confirm(self, operator: object, event: object, title: str = "", message: str = "", confirm_text: str = "",
                       icon: str = "NONE", text_ctxt: str = "", translate: bool = True) -> set[str]
    def invoke_search_popup(self, operator: object) -> None
    def popup_menu(self, draw_func: Callable, title: str = "", icon: str = "NONE") -> None
    def popover(self, draw_func: Callable, *a, **k) -> None
    def popup_menu_pie(self, event: object, draw_func: Callable, title: str = "", icon: str = "NONE") -> None
    def operator_properties_last(self, operator: str) -> object | None
    # remaining functions of the dump (gizmo_*, *__internal, print_undo_steps, tag_script_reload, asset_library_status_*,
    # register_node_group_operators) and the Python members draw_cursor_add/remove -> NotImplementedInQuartz(f"WindowManager.{name}")
    q_modal_handlers: list; q_fileselect_requests: list; q_ui_requests: list
    q_progress: tuple[float, float, float] | None                # (min, max, value) between progress_begin and progress_end
    def q_push_operator(self, op: object) -> None
    def q_new_window(self, scene: "Scene | None" = None) -> Window       # creates and attaches a window
    def _q_trim_windows(self, keep: int = 1) -> None   # internal (Session.reset): discards the windows with index >= keep; keeps the identity of the remaining ones
class BlendDataWindowManagers(IDCollection): ...
class BlendDataScreens(IDCollection): ...
class BlendDataWorkSpaces(IDCollection): ...
# end of module: register_id_type(...) of WindowManager ("WINDOWMANAGER", "window_managers", "WinMan"),
#                Screen ("SCREEN", "screens", "Screen"), WorkSpace ("WORKSPACE", "workspaces", "WorkSpace")
```

1. The three UI collections only have `tag` **[O]** (dump): accessing `new`/`remove` raises
   `AttributeError` with `"has no attribute 'new'"`/`'remove'`; the session links the IDs through
   `_q_construct` + `_q_link` (§2.2.5, item 3).
2. `WindowManager._q_construct(name)` creates exactly **one** `Window` (`scene`, `view_layer`,
   `screen`, `workspace` = `None`; `x = y = 0`, `width = 1920`, `height = 1080` **[I]**,
   `_q_path = "windows[0]"`; Blender in background also has one window: `context.window` is not
   `None` in the `context_semantics` probe **[O]**) — `l2-runtime` depends on this (§2.6.1) — and `keyconfigs` with three
   `KeyConfig` — `default`/`active` `"Blender"`, `addon` `"Blender addon"`, `user` `"Blender
   user"` **[I]** — `keyconfigs.addon is not None` **[O]**. `q_new_window(scene)` (only for tests and
   native code; the session does not use it): appends a `Window` with `scene`, `view_layer =
   scene.view_layers[0]` (or `None`), `_q_path = f"windows[{i}]"`. `_q_trim_windows(keep)` (only
   `Session.reset`, §2.6.1): `keep < 1` -> `ValueError`; removes from the list the windows with index `>=
   keep` (the remaining `Window` objects, and their `_q_path`, stay the same); no stamp **[I]**.
3. `Window.scene = s`: if the current view layer does not belong to `s`, it becomes `s.view_layers[0]` (`None` with
   `s` `None`) **[I]**. `Window.view_layer = vl`: `None` accepted; `vl` that is not in
   `self.scene.view_layers` -> `PropertyValueError` with `"not in scene"` **[I]**. `WindowManager._q_refs`
   = generic + `IDRef(target=w.scene, owner=w, kind="WINDOW_SCENE", counts_user=True,
   on_remove="CLEAR")` per window with a scene (factory scene: 1 user **[O]**); `clear` switches the
   window to the first other scene in `_q_main.scenes`, or `None` **[I]**; `screen`/`workspace`
   do not generate `IDRef` **[I]**.
4. Methods: `modal_handler_add(op)` appends to `q_modal_handlers` and returns `True`;
   `fileselect_add(op)` appends to `q_fileselect_requests`; `invoke_props_dialog/invoke_props_popup/
   invoke_popup/invoke_confirm` append `(name, operator, kwargs)` to `q_ui_requests` and return
   `{"RUNNING_MODAL"}` **[I]**; `invoke_search_popup`, `popup_menu`, `popover`, `popup_menu_pie`
   append and return `None` without calling `draw_func` **[I]**; `event_timer_add` returns a stored
   `Timer` (never fires) and `event_timer_remove` of an absent timer is silent **[I]**;
   `progress_*` only store the state in `q_progress` (`progress_end` -> `None`);
   `operator_properties_last` -> `None`. Other functions of the dump ->
   `NotImplementedInQuartz(f"WindowManager.{name}")`. The items of `q_ui_requests` are 3-tuples
   `(source: str, target: object, payload: object)`; the WindowManager methods write
   `(function_name, operator_or_draw_func, kwargs: dict)` with the arguments received; other
   producers document their own shape (e.g. §2.7.7 writes `("wm.call_menu" | "wm.call_menu_pie",
   menu_name, DrawResult)`). `clipboard` lives only on the instance (NEVER the
   system clipboard). `q_push_operator(op)` appends to `operators` and discards the oldest beyond
   32 **[I]**.
5. `KeyMaps.new`: invalid enums -> `PropertyTypeError`; same `(name, space_type, region_type)`
   returns the existing one **[I]**; `_q_path = f'keymaps["{name}"]'`. `KeyMapItems.new`: validates
   `type`/`value`/`key_modifier`/`direction` against the `KeyMapItem` enums; `id` increasing per keymap
   starting at 1 **[I]**; `head=True` inserts at the start. `new_modal` on a non-modal keymap ->
   `PropertyValueError` with `"not modal"` **[I]**. `KeyConfigurations.remove` of one of the three
   built-in ones -> `PropertyValueError` **[I]**.
6. `KeyMapItem.properties`: `idname` `"mod.op"` -> RNA name `mod.upper() + "_OT_" + op` splitting
   at the **first** `"."` (local conversion, same as that of `quartz.registry.operator_rna_name`, without
   importing it); `idname` without `"."` -> `None`; `cls = quartz.types.resolve_name(rna)`; if `cls` has
   `q_new_properties`, the instance `cls.q_new_properties()` is created once and kept until `idname`
   changes; otherwise `None`.
7. **State**: `WindowManager` adds `"windows"` (list of `{"scene", "view_layer": name,
   "screen", "workspace", "p"}`) and `"clipboard"`; `Screen`/`WorkSpace` only the generic one (the session
   excludes them from the `.qz` and from undo, §2.1.5).

Errors: `AttributeError` (`"has no attribute 'new'"`); `PropertyTypeError` (`'enum "'`);
`PropertyValueError` (`"not modal"`, `"not in scene"`); `NotImplementedInQuartz` (`"WindowManager."`,
`"KeyMapItem.to_string"`).

#### 2.2.11 `quartz/depsgraph.py`

```python
UPDATE_FLAG_CHANNELS: Mapping[str, str] = {"is_updated_transform": "TRANSFORM", "is_updated_geometry": "GEOMETRY",
                                           "is_updated_shading": "SHADING"}
@builtin_struct
class Depsgraph(Struct):
    mode: EnumProperty(items=("VIEWPORT", "RENDER"), ro virt)                 # "VIEWPORT"
    scene, scene_eval: PointerProperty(type=ID, meta fixed_type_name "Scene", ro virt)
    view_layer, view_layer_eval: PointerProperty(type=Struct, meta fixed_type_name "ViewLayer", ro virt)
    ids: tuple[ID, ...]; objects: tuple["Object", ...]; object_instances: tuple["DepsgraphObjectInstance", ...]
    updates: tuple["DepsgraphUpdate", ...]                                    # Python properties
    def update(self) -> None
    def id_eval_get(self, id: ID) -> ID
    def id_type_updated(self, id_type: str) -> bool
    def debug_relations_graphviz(self, filepath: str = "") -> str           # DOT text; never writes to disk [I]
    def debug_stats_gnuplot(self, filepath: str, output_filepath: str) -> None   # no-op
    def debug_tag_update(self) -> None                                          # stamps DATA on all reachable ones [I]
    def debug_stats(self) -> str
@builtin_struct
class DepsgraphUpdate(Struct):           # id (PointerProperty(type=ID) ro virt), is_updated_transform/geometry/shading (ro virt)
@builtin_struct
class DepsgraphObjectInstance(Struct):   # object, instance_object (None), is_instance (False), matrix_world, parent (None),
                                         # persistent_id, random_id, show_self (True), show_particles (False), uv, orco — ro
def depsgraph_for(scene: "Scene", view_layer: "ViewLayer") -> Depsgraph
```

1. `depsgraph_for`: `view_layer` does not belong to `scene` → `PropertyValueError` with `"not in scene"`;
   returns the `Depsgraph` stored on the view layer itself (`_q_depsgraph`; always the same identity),
   created with `_q_last_stamp = dirty_clock()` (a new depsgraph does not see the past **[I]**).
   `ViewLayer.depsgraph` and `ViewLayer.update()` use this function.
2. Reachable items, in order and without repetition: the scene, `scene.world`, the master collection and the collections of the tree
   (pre-order), the objects of `view_layer.objects`, and for each object its `data` (if an ID) and the non-null
   IDs of `data.materials` (if it exists). `ids` = this tuple; `objects` = objects of the view layer with
   `visible_get(view_layer)`; `object_instances` = one `DepsgraphObjectInstance` per item of
   `objects` (`matrix_world` = copy of the object's, `persistent_id` = `(index, 0, 0, 0, 0, 0, 0,
   0)`, `random_id` deterministic **[I]**).
3. `update()`: `now = dirty_clock()`; changed = reachable items for which `q_dirty_since(_q_last_stamp)`
   is non-empty; `_q_last_stamp = now`; with no changed items → nothing is dispatched and `updates` stays as it was
   **[I]**; otherwise `handlers.dispatch("depsgraph_update_pre", scene, self)`, builds `updates` (one
   `DepsgraphUpdate` per changed item, in the order of the reachable items, flags by `UPDATE_FLAG_CHANNELS`; an object
   whose `data` changed in `GEOMETRY`/`SHADING` also enters with those flags, and an object with some
   ancestor (`parent` chain) stamped in `TRANSFORM`/`HIERARCHY` enters with
   `is_updated_transform` **[I]**; the `DepsgraphUpdate` items are new structs, with `_q_set_owner(self,
   f"updates[{i}]")`) and
   `handlers.dispatch("depsgraph_update_post", scene, self)` (arguments `Scene`, `Depsgraph`
   **[O]**). Writes made by the handlers are left for the next `update()`.
4. `id_eval_get(id)` → `id`; `ID.evaluated_get(dg)` → the ID itself (no evaluation in the milestone).
   `id_type_updated(t)`: `t` outside the `ID.id_type` enum → `PropertyTypeError`; true if any
   item of `updates` has that `id_type`. `debug_relations_graphviz` returns `"digraph depsgraph {\n"` +
   one line `f'  "{id.name}";\n'` per item of `ids` + `"}\n"` **[I]**; `debug_stats()` returns
   `f"Approximate {len(ids)} IDs, {len(objects)} objects"` **[I]**; nothing is written to disk.

Errors: `PropertyValueError` (`"not in scene"`); `PropertyTypeError`.

#### 2.2.12 Tests

All in `tests/unit/types/`, without `quartz.session` and without `quartz.testing` (§2.0.1, 4), with local
fixtures: `l2_hooks` (`snap = hooks.snapshot()`; `quartz.types.install_hooks()`; `yield`;
`hooks.restore(snap)`, plus `msgbus.snapshot()/restore()` and `handlers.snapshot()/restore()`),
`data` (`BlendData()` under `l2_hooks`) and `fake_types` (`_q_registry_snapshot()` of `id.py` and
`object.py`; registers fake object data types — module-level `@builtin_struct` classes that subclass `ID`
with `q_bounds`, `materials` (simple list with `append`/`clear`), `q_set_editmode`/`q_flush_edit`
that record a log and, when needed, `q_geometry` from `quartz.geometry.MeshGeometry.from_pydata` —
for types that `l2-datablocks` does not register (`CURVE`, `LATTICE`, …), including with
`register_id_type(..., id_type="CURVE", collection="curves")`; restores on exit; when the test
needs the fake collection in `bpy.data`, `fake_types` runs **before** building the `BlendData`,
because the collections are chosen in `__init__`). The context, when needed, is a
simple object installed with `hooks.install(current_context=...)`. Schema tests import
`quartz.testing.rna_schema_diff`/`function_signature_diff` **inside** the test function (they pass the
gate, §2.4) and define a module-level `DIVERGENCES`; tests that require the real `Mesh` import
`quartz.types.mesh` inside the function (they pass the gate). **[O]** facts come from `blender_facts` and
`blender_dump` (§1.1.2).

- `test_naming.py`: `truncate_utf8` (300 × `N` → 255; 200 × `Ã` → 127 characters/254 bytes **[O]**);
  `split_suffix` (cases from §2.2.2); `unique_name` (empty → default **[O]**, `.001/.002` **[O]**,
  smallest free, base truncated to fit, `.1000`); `sort_key` reproduces `id.order` **[O]**;
  `plan_rename` reproduces `id.rename` **[O]** (ADJUSTED → `QZRN.001`, NO_COLLISION, FORCED with the other
  one at `QZRN.001`), `UNCHANGED`, `UNCHANGED_COLLISION` (`rename_to_existing` **[O]**), `SAME_ROOT` and
  invalid mode (`'enum "'`).
- `test_id.py`: all of §2.2.3 (monotonic clock, `q_tag` with no argument = `DATA`, one stamp per
  call, invalid channel, `q_dirty_since`, nested struct delegation — writing
  `scene.render.resolution_x` stamps the scene —, channel-per-prop table by sampling, `parent` →
  `HIERARCHY`+`TRANSFORM`; `frame_set` does not stamp; `q_dirty` read-only and outside the state);
  `session_uid` unique and increasing; `name`/`rename` (results **[O]**,
  reordering **[O]** `id.order_after_rename`, 255 bytes **[O]**, empty → default, temporary ID only
  truncates); `users` (`use_fake_user` +1 **[O]**; virtual pointer does not generate an `IDRef`:
  `scene.user_of_id(scene.collection) == 0`); `copy` (name `.NNN`, 0 users, same collection
  **[O]**, `Object.copy` shares `data`, temporary ID → NI `"ID.copy"`); removal with tombstone (`"StructRNA of type Object has been removed"`, second
  `remove`, `type(ob).__name__` preserved, `_q_revive`, wrapped `math` of a removed ID with
  `is_valid` false); `user_clear`, `user_remap` (`"same type"`), `user_of_id`, `update_tag`,
  `evaluated_get`, `make_local`; NI with symbol; `repr` with `hooks.install(repr_root=lambda: "bpy")`
  → `"bpy.data.objects['QZD']"` **[O]** and tombstone; direct instantiation → `TypeError`;
  `register_id_type` (no-op, `"already registered"`, `"unknown id_type"`), `id_type_info` by
  class/`id_type`/collection; `_q_state_get/_q_state_set` round trip without stamping (restored name
  repositions the ID in the collection). Schema: `ID` against `id_types["ID"]` (divergences, each one as an
  explicit key of `DIVERGENCES`: `ID.is_runtime_data.flags` — writable in the dump, read-only
  here —, and `ID.name.flags`/`ID.name_full.flags` only if §1.6.4 does not offer a way to declare
  `is_never_none`) and `function_signature_diff` of
  `ID.rename/copy/user_remap/user_of_id/evaluated_get/update_tag/make_local`.
- `test_blenddata.py`: `quartz.types` facade (catalog and `__dir__`; `quartz.types.Object is
  quartz.types.object.Object`; `"_x"` and unknown name → `AttributeError` with the message; resolver
  `set_name_resolver`; `load_builtin_types` tolerates a missing module via `monkeypatch` of
  `BUILTIN_TYPE_MODULES` and propagates `ModuleNotFoundError` for another name; `import quartz.types` in a
  subprocess `[sys.executable, "-c", …]` does not swap hooks or import submodules;
  `on_property_changed` reaches `msgbus.notify_changed` — subscription + `flush()` after writing
  `ob.location`); `BlendData` without a session; 40 attributes in the dump order (`COLLECTION_NAMES` ==
  `data.collections` of the dump), `IMPLEMENTED`, ghost (`note_missing` annotated,
  `f"{P}.data.actions.new"`, `repr`); iteration order **[O]**; `KeyError` **[O]**; `repr` **[O]**
  `"<bpy_collection[3], BlendDataObjects>"`; `new` with duplicate names **[O]**; cascading removal
  `DELETE_OWNER` with a fake type (object disappears, `objects.remove` leaves the data orphaned with 0 users
  **[O]**), `do_unlink=False` (`"must have zero users"`), children without parent, wrong type
  (`"expected a"`) and ID outside the collection (`"not in"`); `batch_remove`,
  `orphans_purge` (count, recursive, scenes and UI preserved), `user_map` (format **[O]**, filters),
  `is_dirty`/`q_mark_clean`/`is_saved`/`filepath` `""` **[O]**, `version` (`== quartz.app.version`
  after `BlendData()`, `q_set_version`, direct write → `ReadOnlyError`), `q_iter_ids` (order,
  built-ins), `q_refs_to`/`q_users_of`, `q_clear(keep=...)` (WM kept with the window at
  `scene = None`). Schema: `BlendData` against
  `sub_structs["BlendData"]`; `new`/`remove`/`tag` of `objects`, `collections`, `scenes`, `worlds`,
  `window_managers`, `screens`, `workspaces` against `data.collections[*]["functions"]`.
- `test_object_transform.py`: `wrap_array` directly (table from §2.2.1 with `PropertyDef` of a fake owner:
  `Vector`, `Euler` with `euler_order`, `Quaternion`, `Color`, `Matrix` without transposing, `PropArray`);
  defaults and messages of `object.defaults` **[O]** (invalid `rotation_mode`, wrong size,
  read-only `type`, unknown attribute, Euler order with `QUATERNION`/`ZYX`, `color`
  as a `PropArray` of 4); formulas of `matrix_basis/local/world` (Euler, quaternion, axis-angle,
  deltas) against `quartz.math`; `Euler((0.1, 0.2, 0.3))` in `rotation_euler` produces the matrix of
  `math.euler_xyz` **[O]**; writing to `matrix_world/local/basis` decomposes **[O]**
  `loc_after_set_world`, including with a parent and negative scale; parent without recomputing the inverse **[O]**
  (`15.0` immediate: declared divergence D9; `matrix_parent_inverse` identity **[O]**); per-component
  write (`ob.matrix_world.translation.x = …`, `ob.location.x = …`) stamps `TRANSFORM`;
  `dimensions` and `bound_box` with fake data (`q_bounds`) and without data (zeros **[O]**);
  `convert_space`; `View3DCursor.matrix`.
- `test_object_misc.py`: `register_object_data_type`/`object_type_for` (errors, MRO, `None` →
  `EMPTY` **[O]**); `data` rules (Empty refuses, wrong type refuses, `None` → `EMPTY`, users:
  data 1 with object **[O]**, object 0 without link and 1 when linked **[O]**); `object_modes_for`,
  `context_mode_for` (table with fake `CURVE`/`LATTICE` data; `EDIT_MESH` **[O]** only in the test that
  imports the real `Mesh` inside the function), `q_set_mode` (order of calls to the fake
  data, invalid mode, stamp), `update_from_editmode`; selection/visibility per view layer
  (with a fake context, without a context using the 1st scene, object outside → `False` **[O]** and `LinkError` `"not
  in View Layer"`); `children`, `children_recursive`, `users_collection`, `users_scene`;
  modifiers (unique name, `persistent_uid`, `move`), constraints and vertex groups (errors and
  fragments); `material_slots` (stable identity per index) and `active_material` with fake data
  (the fake list records the calls: with an existing slot, the slot is replaced via `__setitem__` and
  `clear` is not called; without slots, one `append`); `to_mesh` with fake data of another type (NI) and with the real `Mesh`
  (inside the function); `ray_cast`/`closest_point_on_mesh` with fake `q_geometry` data; NI
  (`"Object.shape_key_add"`); `Object` state (mode, modifiers, groups). Schema: `Object`
  against `id_types["Object"]`, `MaterialSlot` and `Modifier` against `sub_structs`;
  `function_signature_diff` of `Object.select_get/select_set/hide_get/hide_set/visible_get/to_mesh/
  convert_space/ray_cast/closest_point_on_mesh`.
- `test_collection.py`: duplicate `link` **[O]** (`"Object 'QProbeOb' already in collection 'Scene
  Collection'"`), link order **[O]**, missing `unlink`, children (duplicate, cycle, built-in),
  `all_objects`, `children_recursive`, `users_dupli_group`; users (new collection 0, linked 1
  **[O]**); built-in master collection (`is_embedded_data`, name `"Scene Collection"`, outside
  `data.collections`, `repr` **[O]** `"bpy.data.scenes['Scene'].collection"`, fixed name,
  `copy` → NI, `data.collections.remove(master)` → `LinkError`, tombstone together with the scene); `HIERARCHY`
  stamps; removal unlinks from parents and scenes. Schema: `Collection` against
  `id_types["Collection"]`.
- `test_scene_viewlayer.py`: `Scene` defaults (frames 1/250/1, gravity) and of the structs against the
  dump; `frame_set` reproduces `handler_log` **[O]**: scene with an object linked to the master collection, an initial
  `vl.update()` (new depsgraph), handlers `pre(scene, depsgraph=None)`, `post(*args)` and
  `depsgraph_update_post(*args)` registered between `handlers.snapshot()/restore()`, the sequence
  `frame_set(7)`, `vl.update()`, `ob.location.x += 0.0`, `vl.update()`, `frame_set(1)` produces
  exactly `[("frame_change_pre", 7), ("frame_change_post", 2, ["Scene", "Depsgraph"]),
  ("depsgraph_update_post", ["Scene", "Depsgraph"]), ("frame_change_pre", 1),
  ("frame_change_post", 2, ["Scene", "Depsgraph"])]` (the test MUST NOT assert the `depsgraph` of
  `pre`, a divergence from §2.2.8, 6); clamping and `float` refused; view layer of the fake context
  used when `ctx.scene is scene`; `frame_float`/`frame_current_final`; `Scene.objects` and `ViewLayer.objects`
  (pre-order, `exclude`) — tree `Cube, Light, Camera` with empty objects reproduces the order **[O]**;
  `LayerCollection` (identity, flags, `is_visible`, `has_*`), `active_layer_collection`,
  `LayerObjects.active/selected`; `ViewLayers.new/remove/move` (`"at least one"`); `statistics`;
  `ray_cast` with fake data; users of `camera` (does not count **[O]**) and `world` (counts **[O]**);
  `scenes.remove` (`"last"`); state round trip (bases, flags, identity of the view layers; the
  master collection appears as `None` in `"flags"` and never as an instance in the state).
  Schema: `Scene`, `ViewLayer`, `LayerCollection`, `RenderSettings`, `UnitSettings`
  (divergence `UnitSettings.scale_length.default`: dump 0.0 below the minimum), `ToolSettings`,
  `View3DCursor`; `function_signature_diff` of `Scene.frame_set/statistics/ray_cast` and
  `ViewLayer.update`.
- `test_world_wm.py`: `World` (default color, wrapped `Color`, 0 → 1 user via `scene.world`
  **[O]**, `SHADING` also via `light_settings`, `light_settings`/`mist_settings`); `WindowManager`
  built by `_q_construct("WinMan")` + `_q_link` has exactly one `Window` with everything `None`;
  `q_new_window`; `Window.scene`/`view_layer` (automatic switch, `"not in scene"`); `WINDOW_SCENE`
  (scene with a window has 1 user **[O]**; removing the scene switches the window to the other one, or `None`);
  `keyconfigs` (three built-in, `addon` not `None`
  **[O]**), `KeyMaps.new/find/remove`, `KeyMapItems.new/new_modal/remove/from_id` (invalid enums,
  `head`, `"not modal"`, `new_from_item`, `find_from_operator`); `KeyMapItem.compare`, `to_string`
  → NI; `KeyMapItem.properties` with a fake resolver (class with `q_new_properties`; idname
  `"mod.op"` → lookup `"MOD_OT_op"`), without a class and without `"."` → `None`; headless methods (`modal_handler_add` → `True`,
  `fileselect_add`, `invoke_*` → `{"RUNNING_MODAL"}` with the tuple recorded in `q_ui_requests`, timers
  that do not fire, `q_progress`, in-memory `clipboard`, `q_push_operator` limited to 32, a
  dump function that is not implemented → NI `"WindowManager."`); `window_managers.new` → `AttributeError` **[O]**;
  `Screen`/`WorkSpace`. Schema: `World` against `id_types["World"]`; `WindowManager`, `KeyMap`,
  `KeyMapItem` against `sub_structs`; `function_signature_diff` of the implemented functions of
  `WindowManager` against `sub_structs["WindowManager"]["functions"]`.
- `test_depsgraph.py`: `depsgraph_for` (identity, foreign view layer); `update()` without changes does not
  dispatch **[I]** and after writing `ob.location` dispatches `pre`/`post` with `(Scene,
  Depsgraph)` **[O]**; flags per channel (`TRANSFORM`, `GEOMETRY` via fake data, `SHADING`), object
  enters when the data changes, child enters with `is_updated_transform` when the parent moves; write
  inside the handler is left for the next `update()`; `updates` persists; `ids` (order), `objects`
  (visible only), `object_instances`; `id_eval_get`, `evaluated_get`, `id_type_updated` (invalid
  enum); `debug_relations_graphviz` returns `str` without creating a file, `debug_stats`; new depsgraph
  ignores earlier stamps.
  Schema: `Depsgraph`, `DepsgraphUpdate` against `sub_structs`; `function_signature_diff` of
  `Depsgraph.update/id_eval_get/id_type_updated`.

### 2.3 Data-blocks (`l2-datablocks`)

Modules `quartz.types.mesh`, `material`, `camera`, `light`, `image`, `text`. They import L1 and, from L2,
**only** `quartz.types.id` (`ID`, `register_id_type`, `DIRTY_CHANNELS`), `quartz.types.blenddata`
(`IDCollection`, `BlendData`), `quartz.types.object` (`Object`, `register_object_data_type`)
(§0.6) and the sibling modules of this task (e.g. `mesh` imports `material` to validate
`IDMaterials.append`/`__setitem__`, §2.3.1, rule 17). L1 names used: `quartz.rna` (`Struct`, `builtin_struct`, `PropCollection`, `PropArray`,
`IDRef`, `get_property`, `hooks`), `quartz.props` (factories and `meta`), `quartz.geometry`
(`MeshGeometry`, `AttributeStore`, `AttributeArray`, `DATA_TYPES`, `DOMAINS`, `REQUIRED_ATTRIBUTES`,
`default_fill`, `calc_edges`,
`edge_keys`, `face_edge_keys`, `loose_edges`, `flip_faces`, `face_normals`, `vertex_normals`,
`corner_normals`, `face_centers`, `face_areas`, `triangulate`, `transform_points`, `bounds`),
`quartz.math` (`Vector`, `Matrix`), `quartz.errors`, `quartz.app.settings`, `quartz.path.basename`.

Rules common to the six subsections:

1. **Classes**: every RNA class in this section is `@builtin_struct` with `_q_strict_attrs = True` (the
   IDs inherit from `ID`). Each module defines `__all__` with the RNA classes, the collections, and the public functions and
   constants listed in its signature block; names starting with `_` are internal.
2. **Declaration rule**: except for exceptions listed in the subsection, each type declares as a `PropertyDef`
   **all** the `BOOLEAN`/`INT`/`FLOAT`/`STRING`/`ENUM` props of its dump entry (`id_types` or
   `sub_structs`), with name, subtype, unit, size, default, limits, `step`, `precision`,
   `maxlen` (= `length_max`) and items from the dump, plus the `is_readonly` flags (computed props without a
   setter) and `is_never_none` from the dump (§2.4). Computed props use `meta={"virtual_get": ...,
   "virtual_set": ...}` and declare the dump default (§2.4.5, item 3). `POINTER`/`COLLECTION` props
   follow the form indicated in each type: `PropertyDef`, Python property (Python data descriptor;
   §2.2, top rule 3) or absent.
3. **Dirty channels** (`meta["dirty"]`, §2.2.3) of this section — normative:

| Write | Channel |
|---|---|
| mesh element props (`co`, `vertices`, `loop_start`, `vertex_index`, `edge_index`, `use_seam`, `use_edge_sharp`, `use_smooth`, `material_index`, `uv`, `pin_uv`), attribute and UV data, structural `Mesh` operations (`from_pydata`, `update`, `add`, `foreach_set` of an attribute that is not `select`/`select_edge`/`hide`, `transform`, `flip_normals`, `shade_*`, `clear_geometry`, `split_faces`, `q_set_geometry`, leaving edit mode) | `"GEOMETRY"` |
| `Attribute.name`, `MeshUVLoopLayer.name`, `AttributeGroupMesh.new/remove`, `UVLoopLayers.new/remove`, `validate_material_indices` (if it changed something), `pin_ensure` (if it created something) | `"GEOMETRY"` **[I]** |
| `select`/`select_edge` of elements and writes to `.select_*`/`.uv_select_*` attributes | `"SELECT"` |
| `hide` of elements and `.hide_*` attributes | `"VISIBILITY"` |
| `Mesh.materials` (`append`, `pop`, `clear`, `__setitem__`; `pop`/`clear` that change `material_index` also stamp `"GEOMETRY"`), all props of `Material` and `Light` (including `type`) | `"SHADING"` **[I]** for Light |
| other props of `Mesh`, `Camera`, `CameraDOFSettings`, `Image`, `Text`, `AttributeGroupMesh`, `MeshUVLoopLayer.active/active_render/active_clone`, `UVLoopLayers.active*` and writes to pixels/lines | `"DATA"` |

   A write to attribute data via `Attribute.data`/`foreach_set`/`MeshUVLoopLayer.*` stamps the channel
   by the attribute **name**: `.select_*`/`.uv_select_*` → `"SELECT"`, `.hide_*` → `"VISIBILITY"`,
   others → `"GEOMETRY"`.

4. **Element proxies** (`MeshVertex`, `MeshEdge`, `MeshLoop`, `MeshPolygon`,
   `MeshLoopTriangle`, `MeshNormalValue`, `ReadOnlyInteger`, `*AttributeValue`, `MeshUVLoop`,
   `TextLine`): created by `cls._q_new_child(owner, path)` (§1.6.7) with `_q_index: int`; they are
   new *flyweights* on each access — with no identity guarantee (`mesh.vertices[0] is
   mesh.vertices[0]` is false **[I]**), with `__eq__` true for the same class, the same owner (`is`)
   and the same index, and `__hash__` = `hash((type(self), id(owner), index))`. Their props are all
   virtual over the owner's storage; a write delegates the dirtying to the ID via `Struct._q_on_change`
   (§1.6.7). Index beyond the current size of the domain → `IndexError` (at creation and on each later
   access, if the domain shrank). Removed owner → the tombstone's `RemovedStructError` (§2.1.4) when
   touching the owner.
5. **Collections and layer proxies** (`MeshVertices`…, `AttributeGroupMesh`, `UVLoopLayers`,
   `IDMaterials`, `Attribute`, `MeshUVLoopLayer`, `Text.lines`) are created once per ID and
   stored (stable identity); `Attribute`/`MeshUVLoopLayer` are stored by attribute name
   (lifetime rule in "Element and layer rules", item 7). Element collections (`MeshVertices`,
   `MeshEdges`, `MeshLoops`, `MeshPolygons`, `MeshLoopTriangles`, the three normals ones,
   `loop_triangle_polygons`, `Attribute.data`, `MeshUVLoopLayer.data/uv/pin`, `Text.lines`) MUST
   override `__len__` (size of the domain, without creating proxies), `__getitem__` (`int`/negative/`slice`;
   `str` → `KeyError` from §1.6.5) and `__iter__` (proxies created one at a time), and `__contains__` for
   non-`str` using `==` (not identity, since the proxies are new on each access); `keys()` → `[]`.
   Collections with an ID owner have `__repr__` = `f"{repr(id)}.{path}"` (e.g.
   `"bpy.data.meshes['Cube'].vertices"`) **[I]**; the `repr` of a proxy follows `Struct.__repr__`
   (`"bpy.data.meshes['Cube'].vertices[0]"` **[O]**).
6. **Internal fields** of each ID are created in the class's `_q_construct` (which extends the one from `ID`,
   §2.2.4); an instance created only by `Struct.__new__` is not supported. Writable native members
   (`Mesh.q_edit_data`) are data descriptors (the class is strict).
7. **Creation in the collections**: each `BlendData<Type>.new` calls `IDCollection.new(self, name)`
   (§2.2.5: unique name, `_q_construct`, link) and then configures the instance. Each collection
   overrides `remove` with the parameter name from the dump, delegating to `IDCollection.remove` (rules from
   §2.1.4):
   `def remove(self, <mesh|material|camera|light|image|text>: ID, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None`.
8. **State** (§2.1.5): each type extends `_q_state_get`/`_q_state_set` with the keys listed
   in its subsection; arrays are copied in both directions; `_q_state_set` does not stamp dirtiness or
   call hooks. `q_schema_version = 1` in all types.
9. **End of module** (the only import effects, §2.0.2): `register_id_type(...)` with the values from the
   `# end` comment in the signature block of each subsection (§2.3.1–§2.3.6) and, in `mesh`/`camera`/`light`, `register_object_data_type(...)`.

#### 2.3.1 `quartz/types/mesh.py`

```python
@builtin_struct
class Mesh(ID):
    # PropertyDef (rule 2): all scalar/array props of id_types["Mesh"]; computed (virt, ro):
    #   normals_domain, has_custom_normals (False), total_vert_sel, total_edge_sel, total_face_sel, is_editmode
    # Python properties (Python data descriptor; §2.2, rule 3 from the top): vertices, edges, loops, polygons, loop_triangles, loop_triangle_polygons, attributes,
    #   color_attributes, uv_layers, vertex_normals, polygon_normals, corner_normals, materials, shape_keys (always None),
    #   animation_data (always None)
    # vertex_colors, skin_vertices: Python properties whose read raises NI f"Mesh.{name}"
    # missing (AttributeError, strict class): texture_mesh, texco_mesh, uv_layer_clone, uv_layer_stencil, cycles
    edge_keys: list[tuple[int, int]]                       # python member: one key (min, max) per edge, in edge order
    def from_pydata(self, vertices, edges, faces, shade_flat: bool = True) -> None
    def update(self, calc_edges: bool = False, calc_edges_loose: bool = False) -> None
    def validate(self, verbose: bool = False, clean_customdata: bool = True) -> bool
    def validate_material_indices(self) -> bool
    def clear_geometry(self) -> None
    def transform(self, matrix, shape_keys: bool = False) -> None
    def flip_normals(self) -> None
    def shade_flat(self) -> None
    def shade_smooth(self) -> None
    def set_sharp_from_angle(self, angle: float = 0.523599) -> None
    def calc_loop_triangles(self) -> None
    def split_faces(self) -> None
    def count_selected_items(self) -> tuple[int, int, int]
    def update_gpu_tag(self) -> None                        # no-op
    def free_tangents(self) -> None                         # no-op
    def calc_tangents(self, *a, **k) -> NoReturn            # NI "Mesh.calc_tangents"
    def calc_smooth_groups(self, *a, **k) -> NoReturn       # NI
    def normals_split_custom_set(self, *a, **k) -> NoReturn # NI
    def normals_split_custom_set_from_vertices(self, *a, **k) -> NoReturn   # NI
    def unit_test_compare(self, *a, **k) -> NoReturn        # NI
    # vertex_creases, vertex_creases_ensure, vertex_creases_remove, edge_creases, edge_creases_ensure, edge_creases_remove,
    # vertex_paint_mask, vertex_paint_mask_ensure, vertex_paint_mask_remove: members that raise NI f"Mesh.{name}"
    # ---- native ----
    q_geometry: MeshGeometry                                # ro (descriptor); the source of truth; live views
    def q_set_geometry(self, geo: MeshGeometry) -> None
    def q_tag_geometry(self) -> None                        # = self.q_tag("GEOMETRY")
    def q_bounds(self) -> tuple[np.ndarray, np.ndarray]     # quartz.geometry.bounds(positions) in float64; empty -> zeros
    q_edit_data: object | None                              # rw (descriptor); opaque, held by quartz.bmesh
    def q_set_editmode(self, state: bool) -> None
    def q_flush_edit(self) -> bool

def set_editmode_hooks(*, enter: Callable[[Mesh], None] | None = None,
                       flush: Callable[[Mesh], None] | None = None) -> None
    # replaces BOTH module hooks; each None restores the default (no-op); set_editmode_hooks() = defaults

class MeshVertices(PropCollection):   def add(self, count: int) -> None
class MeshEdges(PropCollection):      def add(self, count: int) -> None
class MeshLoops(PropCollection):      def add(self, count: int) -> None
class MeshPolygons(PropCollection):   def add(self, count: int) -> None
    active: int                       # python rw (collection_api of the dump); index of the active face, default 0; only stored [I]
class MeshLoopTriangles(PropCollection): ...           # read-only

@builtin_struct
class MeshVertex(Struct):     # co (TRANSLATION 3, rw), normal (ro), select, hide, index (ro), undeformed_co (ro) — PropertyDef virt
    groups: PropCollection    # python; always empty (group weights live outside the mesh in the milestone) [I]
@builtin_struct
class MeshEdge(Struct):       # vertices (INT 2, rw), select, hide, use_seam, use_edge_sharp, is_loose (ro), index (ro)
    key: tuple[int, int]      # python member: (min, max)
@builtin_struct
class MeshLoop(Struct):       # vertex_index, edge_index (rw), index, normal, tangent, bitangent, bitangent_sign (ro)
@builtin_struct
class MeshPolygon(Struct):    # loop_start (rw), loop_total (ro), material_index, use_smooth, select, hide (rw), normal, center, area, index (ro)
    vertices: PropArray       # python (dynamic size; exception to rule 2): live view of corner_verts[loop_start:loop_start+loop_total]
    edge_keys: list[tuple[int, int]]   # python member
    loop_indices: range       # python member [I]
    def flip(self) -> None
@builtin_struct
class MeshLoopTriangle(Struct):   # vertices, loops (INT 3), polygon_index, normal, split_normals (3x3), area, index, material_index, use_smooth — all ro
    center: Vector                # python member
    edge_keys: list[tuple[int, int]]
@builtin_struct
class MeshNormalValue(Struct):    # vector (FLOAT DIRECTION 3, ro)
@builtin_struct
class ReadOnlyInteger(Struct):    # value (INT, ro)

@builtin_struct(identifier="AttributeGroupMesh")
class AttributeGroupMesh(PropCollection):
    # PropertyDef virt (rw): active_index, active_color_index, render_color_index, active_color_name, default_color_name
    active: "Attribute | None"            # python rw
    active_color: "Attribute | None"      # python rw
    def new(self, name: str, type: str, domain: str) -> "Attribute"
    def remove(self, attribute: "Attribute") -> None
    def domain_size(self, domain: str) -> int
@builtin_struct
class Attribute(Struct):          # name (rw), data_type, storage_type ("ARRAY"), domain, is_internal, is_required (ro) — PropertyDef virt
    data: PropCollection          # python; items of the value class of data_type (table below)
    def q_array(self) -> np.ndarray   # the current AttributeArray.data, no copy (live view until the domain changes size)
# value classes (one item per domain element), all @builtin_struct with virt props over the array row:
class FloatAttributeValue(Struct)        # value (FLOAT)                      <- FLOAT
class IntAttributeValue(Struct)          # value (INT)                        <- INT
class ByteIntAttributeValue(Struct)      # value (INT, -128..127)             <- INT8
class BoolAttributeValue(Struct)         # value (BOOLEAN)                    <- BOOLEAN
class FloatVectorAttributeValue(Struct)  # vector (FLOAT XYZ 3 -> Vector)     <- FLOAT_VECTOR
class Float2AttributeValue(Struct)       # vector (FLOAT XYZ 2 -> Vector)     <- FLOAT2
class FloatColorAttributeValue(Struct)   # color, color_srgb (FLOAT COLOR 4)  <- FLOAT_COLOR
class ByteColorAttributeValue(Struct)    # color, color_srgb (FLOAT COLOR 4)  <- BYTE_COLOR
class QuaternionAttributeValue(Struct)   # value (FLOAT QUATERNION 4)         <- QUATERNION
class Float4x4AttributeValue(Struct)     # value (FLOAT MATRIX 4x4)           <- FLOAT4X4
class Short2AttributeValue(Struct)       # value (INT 2)                      <- INT16_2D
class Int2AttributeValue(Struct)         # value (INT 2)                      <- INT32_2D

class UVLoopLayers(PropCollection):
    active: "MeshUVLoopLayer | None"; active_index: int        # python rw
    active_render: "MeshUVLoopLayer | None"; active_render_index: int
    def new(self, name: str = "UVMap", do_init: bool = True) -> "MeshUVLoopLayer | None"
    def remove(self, layer: "MeshUVLoopLayer") -> None
@builtin_struct
class MeshUVLoopLayer(Struct):    # name (STRING maxlen 64), active, active_render, active_clone — PropertyDef virt
    data: PropCollection          # python; MeshUVLoop items
    uv: PropCollection            # python; Float2AttributeValue items (.vector)
    pin: PropCollection           # python; BoolAttributeValue items (.value)
    def pin_ensure(self) -> "Attribute"        # creates `.pn.<name>` (CORNER, BOOLEAN) if missing; returns its Attribute
                                               # (the dump declares a BoolAttribute output [O]; here the class is Attribute, item 7)
@builtin_struct
class MeshUVLoop(Struct):         # uv (FLOAT XYZ 2), select, select_edge, pin_uv (BOOLEAN)

class IDMaterials(PropCollection):
    def append(self, material: "Material | None") -> None
    def pop(self, index: int = -1) -> "Material | None"
    def clear(self) -> None
    def __setitem__(self, index: int, material: "Material | None") -> None

class BlendDataMeshes(IDCollection):
    def new(self, name: str) -> Mesh
    def new_from_object(self, object: Object, preserve_all_data_layers: bool = False, depsgraph: object = None) -> Mesh
    def remove(self, mesh: Mesh, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None
# end of module: register_id_type(Mesh, id_type="MESH", collection="meshes", default_name="Mesh", collection_cls=BlendDataMeshes)
#                register_object_data_type(Mesh, "MESH")
```

**Storage.** `_q_construct` creates `_q_geometry = MeshGeometry()`, `_q_materials: list[Material
| None] = []`, `_q_layers = {"uv_active": None, "uv_render": None, "attr_active": None,
"color_active": None, "color_render": None}` (attribute names), `_q_editmode = False`,
`_q_edit_data = None` and empty caches. Derived caches (normals, centers, areas, triangles,
loose edges) are stored with the stamp `self.q_dirty["GEOMETRY"]` and recomputed when the
stamp changes; anyone who writes directly to `q_geometry` MUST call `q_tag_geometry()`. Paths that do not
stamp (`_q_state_set`) empty the caches explicitly.

**Normalization of `_q_layers`** (done on reading any "active"/"render" member and at the end of
`from_pydata`, `clear_geometry`, `q_set_geometry`, `_q_state_set`, `remove` and renaming): an
entry whose name no longer exists in the `AttributeStore`, or exists with an incompatible domain/type (UV:
non-internal `CORNER`/`FLOAT2`; color: non-internal `FLOAT_COLOR`/`BYTE_COLOR` on `POINT`/`CORNER`), becomes
`None`; then, `uv_active`/`uv_render` that are `None` while some UV map exists move to the first UV map
in store order **[I]**. Color entries and `attr_active` are not filled in automatically.

**Mapping table** (source of the proxies and fast path of `foreach_get/foreach_set`; `—` =
read-only). Attributes marked with `*` are created on demand on the first write
(`AttributeStore.new` with the default fill); before that, reading returns the default (`False`/`0`):

| Collection | Item attribute | Source | Items per element | Write |
|---|---|---|---|---|
| `vertices` | `co`, `undeformed_co` | `position` | 3 | `co` yes; `undeformed_co` — |
| | `normal` | `vertex_normals(geo)` | 3 | — |
| | `select` / `hide` | `.select_vert`* / `.hide_vert`* (POINT, BOOLEAN) | 1 | yes |
| | `index` | `arange(V)` | 1 | — |
| `edges` | `vertices` | `.edge_verts` | 2 | yes |
| | `select` / `hide` | `.select_edge`* / `.hide_edge`* (EDGE, BOOLEAN) | 1 | yes |
| | `use_seam` / `use_edge_sharp` | `uv_seam`* / `sharp_edge`* (EDGE, BOOLEAN) **[I]** | 1 | yes |
| | `is_loose` | `loose_edges(geo)` | 1 | — |
| `loops` | `vertex_index` / `edge_index` | `.corner_vert` / `.corner_edge` | 1 | yes |
| | `normal` | `corner_normals(geo, sharp_face=…)` | 3 | — |
| | `tangent`, `bitangent` / `bitangent_sign` | zeros **[I]** | 3 / 1 | — |
| `polygons` | `loop_start` | `face_offsets[:-1]` | 1 | yes (`set_face_offsets`) |
| | `loop_total` | `face_sizes()` | 1 | — |
| | `vertices` | `.corner_vert` in face order | total = number of corners **[O]** | yes |
| | `material_index` | `material_index`* (FACE, INT) **[I]** | 1 | yes |
| | `use_smooth` | `not sharp_face` (absent = smooth) | 1 | yes (creates `sharp_face` if missing) |
| | `select` / `hide` | `.select_poly`* / `.hide_poly`* (FACE, BOOLEAN) | 1 | yes |
| | `normal` / `center` / `area` | `face_normals` / `face_centers` / `face_areas` | 3 / 3 / 1 | — |
| `loop_triangles` | `vertices`, `loops`, `polygon_index`, `normal`, `split_normals`, `area`, `material_index`, `use_smooth`, `index` | `triangulate(geo)` + derived | 3, 3, 1, 3, 9, 1, 1, 1, 1 | — |
| `vertex_normals` / `polygon_normals` / `corner_normals` | `vector` | normals above | 3 | — |
| `loop_triangle_polygons` | `value` | `tri_face` of `triangulate` | 1 | — |
| `Attribute.data` | `value` / `vector` / `color` / `color_srgb` | `AttributeArray.data` | shape from `DATA_TYPES` | yes |
| `MeshUVLoopLayer.data` | `uv` / `pin_uv` / `select` / `select_edge` | `<name>` / `.pn.<name>`* / `.uv_select_vert`* / `.uv_select_edge`* **[I]** | 2 / 1 / 1 / 1 | yes |
| `MeshUVLoopLayer.uv` / `.pin` | `vector` / `value` | `<name>` / `.pn.<name>`* | 2 / 1 | yes |

`.uv_select_vert`/`.uv_select_edge` (`CORNER`, `BOOLEAN`) belong to the mesh, shared by all
UV maps **[I]**; `.pn.<name>` is per map (`CORNER`, `BOOLEAN`).

**`foreach_get(attr, seq)` / `foreach_set(attr, seq)`** on the collections in the table:

1. An `attr` that is not in the collection's table and is not a `PropertyDef` of the item class →
   `AttributeError` with `"has no attribute"` (even with the collection empty) **[I]**; an `attr` in the table
   (including Python members such as `polygons.vertices`) uses the fast path; an `attr` outside the table
   but declared as a `PropertyDef` on the item → generic path of §1.6.5.
2. `seq` is a `list` (or other mutable sequence) or an `np.ndarray` of any dtype and shape; the total
   number of elements MUST be `len(collection) × items per element` (for `polygons.vertices`, the number of
   corners), otherwise `PropertyValueError` with `"sequence size mismatch"` (§1.6.5).
3. `foreach_get`: an ndarray receives the copy with `casting="unsafe"` (ndarray accepted **[O]**,
   `probes.id_semantics.foreach_get_numpy`; any dtype, e.g. `float32`/`float64`/`int32`/`bool`, **[I]**);
   a list receives Python values (`float`/`int`/`bool`) by slice assignment, without changing its size.
   Values **[O]**: quad `(0,0,0),(1,0,0),(1,1,0),(0,1,0)` → `co` = `[0,0,0, 1,0,0, 1,1,0, 0,1,0]`.
4. `foreach_set`: writing to a read-only source → `ReadOnlyError` with `"is read-only"` **[I]**;
   otherwise converts to the storage dtype (`casting="unsafe"`; boolean = value ≠ 0), writes, stamps
   the channel from rule 3 and invalidates the caches. `polygons.loop_start` writes with
   `MeshGeometry.set_face_offsets` (`ValueError` becomes `PropertyValueError` with the same message).
   A missing attribute marked `*` is created before writing. Does not notify the msgbus **[I]**.
5. The validation order is: `attr` (item 1), read-only (item 4), size (item 2); nothing is
   written if any of them fails.

**`Mesh` rules:**

1. `from_pydata(vertices, edges, faces, shade_flat=True)`: replaces the geometry with
   `MeshGeometry.from_pydata(vertices, edges, faces, shade_flat=shade_flat)` (divergence **[I]**:
   Blender requires an empty mesh); an L1 `ValueError` becomes `PropertyValueError` with the same message and
   `__cause__` (nothing changes on failure). Materials stay; `_q_layers` goes through normalization. Quad → 4 v / 4 e / 4 loops /
   1 face **[O]**; `validate()` afterwards → `False` **[O]**; attributes (as a set of `(name,
   domain, type)`) = the 8 from `probes.id_semantics.from_pydata_attributes` **[O]**; `polygons[0]`:
   `loop_start 0`, `loop_total 4`, `vertices [0,1,2,3]`, `edge_keys [(0,1),(1,2),(2,3),(0,3)]` **[O]**;
   `edge_keys` as a set = `{(0,3),(0,1),(1,2),(2,3)}` **[O]** (own order, divergence 6 of
   ARCHITECTURE §13). Triangle with `shade_flat=True` → `use_smooth False`; `shade_flat=False` →
   `True` **[O]** (`mesh.shade`). Stamps `"GEOMETRY"`.
2. `update(calc_edges, calc_edges_loose)`: if `calc_edges`, or if there are faces and no edges,
   `calc_edges(geo, keep_existing=True)` **[I]**; `calc_edges_loose` does nothing further (loose
   edges are derived). Always stamps `"GEOMETRY"`.
3. `validate(verbose, clean_customdata)`: `changed, problems = geo.validate(fix=True)`; with
   `verbose`, prints each problem on its own line to `sys.stdout`; returns `changed` (correct mesh →
   `False` **[O]**); if it changed, stamps `"GEOMETRY"`.
4. `validate_material_indices()`: `material_index` values ≥ `max(len(materials), 1)` become 0;
   returns whether anything changed **[I]**.
5. `clear_geometry()`: new empty geometry (`MeshGeometry()`, required attributes only; UVs and other
   attributes disappear); materials stay **[I]**; `_q_layers` reset.
6. `transform(matrix, shape_keys=False)`: `matrix` = `Matrix` or a 4×4 sequence (nested or flat of
   16), otherwise `PropertyValueError` with `"4x4"`; `positions[:] = transform_points(positions, m)`
   (computed in float64, stored as float32); `shape_keys` ignored; does not flip the winding **[I]**.
7. `flip_normals()` = `flip_faces(geo)`; `MeshPolygon.flip()` = `flip_faces(geo, mask)` for that face only.
8. `shade_flat()`: `sharp_face` = true on all faces (created if missing). `shade_smooth()`:
   removes `sharp_face` and `sharp_edge` if they exist (`use_smooth` reads true) **[I]**. Both
   exist in 5.2 **[O]**.
9. `set_sharp_from_angle(angle)`: recreates `sharp_edge` (EDGE, BOOLEAN): an edge with exactly two
   faces is sharp if the angle between the face normals is greater than `angle`; other edges are
   false **[I]**. Does not change `sharp_face`.
10. `split_faces()`: corners of the same vertex in neighboring faces (that share an edge
    containing the vertex) stay joined if both faces are smooth and the edge is not `sharp_edge`; each
    group of corners gets its own vertex (the first group keeps the index; new vertices go
    to the end, copying the `POINT` attributes); edges recomputed **[I]**.
11. `calc_loop_triangles()` forces the cache to be recomputed; `loop_triangles` works even without the
    call (computed on demand). Triangles = `triangulate(geo)`; `normal` = triangle normal,
    `split_normals` = the 3 corner normals, `center` = mean, `edge_keys` = the 3 sorted keys
    `(v0,v1), (v1,v2), (v0,v2)` **[I]**.
12. `normals_domain`: `"FACE"` if there are faces and all are flat; `"POINT"` if no face is flat and
    there is no `sharp_edge` edge; otherwise `"CORNER"`; no faces → `"POINT"` **[I]**. `sharp_edge` does not
    enter the corner normal calculation (divergence **[I]**).
13. `count_selected_items()` → `(number of true .select_vert, number of true .select_edge, number of true .select_poly)`;
    `total_vert_sel`/`total_edge_sel`/`total_face_sel` are equal; a missing attribute counts 0 (meshes
    from `meshes.new`, `clear_geometry` or from the `vertices/loops/polygons.add` flow only have the four
    required attributes, §1.5.2).
14. Non-geometric props from the dump (`remesh_*`, `use_mirror_*`, `radial_symmetry`, `use_paint_*`,
    `use_auto_texspace`, `auto_texspace`, `texspace_location`, `texspace_size`,
    `uv_layer_clone_index`, `uv_layer_stencil_index`) are stored with no effect; the texture space
    is not recomputed (divergence **[I]**).
15. `q_set_geometry(geo)`: a non-`MeshGeometry` → `PropertyTypeError` with `"MeshGeometry"`; adopts without
    copying (the caller MUST NOT reuse `geo` in another mesh); empties caches, invalidates the layer
    proxies, normalizes `_q_layers` and stamps `"GEOMETRY"`; does not change the edit mode or
    `q_edit_data` (the L3 `flush` hook MAY use it to write back the BMesh).
16. **Edit mode** (§2.1.9): `q_set_editmode(state)` converts `state` with `bool()`.
    `q_set_editmode(True)` outside edit mode → `_q_editmode = True` (`is_editmode` reads true
    **[O]**, `modes.mesh_is_editmode`) and then calls the `enter(self)` hook; if `enter` raises,
    `_q_editmode` goes back to `False` and the exception propagates; entering does not stamp. `q_set_editmode(False)` in
    edit mode → `flush(self)` hook if `q_edit_data` is not `None` (if `flush` raises, the exception
    propagates and nothing changes: it remains in edit mode with the same `q_edit_data`), then `q_edit_data = None`,
    `_q_editmode = False`, stamps `"GEOMETRY"`; requesting the current state is a no-op (no hook, no
    stamp). `q_flush_edit()`: in edit mode with `q_edit_data` not `None` → `flush(self)` (exception
    propagates), stamps `"GEOMETRY"`, returns `True`; otherwise returns `False` with no effect. The hooks are
    read from the module at call time (a swap through `set_editmode_hooks` applies to the next
    call). Without L3 (default hooks), entering edit mode only marks the state.
17. **Materials**: `materials` is `IDMaterials` over `_q_materials` (item `Material` or `None`;
    key = material name; `None` has no key). Validation common to `append`/`__setitem__`: removed
    ID (`getattr(type(m), "_q_removed", False)`) → `RemovedStructError` with `"has been
    removed"`; `m` neither `Material` nor `None` → `PropertyTypeError` with `f"expected a Material type,
    not {type(m).__name__}"`. `append(m)`: appends. `pop(index=-1)`: index (negatives allowed) out of range →
    `IndexError` with `"out of range"`; removes and returns the slot; faces with `material_index > index`
    are decremented **[I]**. `clear()` empties the slots and removes the `material_index` attribute (face
    indices go back to 0) **[I]**. `__setitem__(index, m)` replaces the slot (`IndexError` with `"out of
    range"` when out of range). A newly created material has 0 users and 1 after `append` **[O]**
    (`id.users.mat_new`, `mat_after_mesh_append`).
18. `_q_refs()` = `super()._q_refs()` + one `IDRef(target=material, owner=self, kind="MATERIAL",
    counts_user=True, on_remove="CLEAR", clear=..., remap=...)` per non-`None` slot, in slot
    order (the same material in two slots counts 2 **[I]**); `clear()` sets that slot to `None`,
    `remap(new)` replaces that slot (§2.1.4); neither changes `material_index`.
19. `_q_copy_into(new)`: `super()._q_copy_into(new)` and then `new._q_geometry =
    self._q_geometry.copy()`, `new._q_materials = list(...)`, `new._q_layers = dict(...)`, edit mode
    off and `q_edit_data = None` (`Mesh.copy()` copies the geometry, §2.1.4).
20. **State**: keys `"mesh_geometry"` (`{"face_offsets": ndarray, "attributes": [{"name",
    "domain", "data_type", "data": ndarray}, ...]}` in `AttributeStore` order), `"mesh_materials"`
    (list of `Material | None`), `"mesh_layers"` (the `_q_layers` dict), `"mesh_editmode"` (`bool`).
    `_q_state_set` rebuilds an equivalent `MeshGeometry` (same names, order, domains, types,
    data and offsets), resets `q_edit_data`, empties caches, invalidates the `Attribute`/
    `MeshUVLoopLayer` proxies (item 7 of the layer rules) and does not call edit hooks.
21. `Mesh` does not declare its own `_q_on_change` (the one from `ID` stamps `meta["dirty"]`).

**Element and layer rules:**

1. `MeshPolygon.vertices`: reading → `PropArray` over the live slice of `.corner_vert` (writing by
   index stamps `"GEOMETRY"`); assigning a sequence with size ≠ `loop_total` →
   `PropertyValueError` with `"loop_total"`. `MeshPolygon.loop_start =` rewrites the offsets
   (`set_face_offsets`; decreasing → `PropertyValueError`).
2. `MeshVertices/Edges/Loops/Polygons.add(count)`: `count < 0` → `PropertyValueError` with
   `"count"`; L1's `add_verts/add_edges/add_corners/add_faces(count)` (empty faces at the end);
   stamps `"GEOMETRY"`. Low-level flow **[I]**: `vertices.add`, `loops.add`, `polygons.add`,
   `foreach_set("co"/"vertex_index"/"loop_start")`, `update(calc_edges=True)` produces the same
   counts, positions, `polygons[i].vertices` and the same set of `edge_keys` as `from_pydata`.
3. `attributes` iterates **all** attributes, including internal ones with `.` (the set of
   `(name, domain, type)` is **[O]**, `probes.id_semantics.from_pydata_attributes`), in the order of the
   `AttributeStore` (Blender's order is different; divergence **[I]**); key = name.
   `color_attributes` iterates only non-internal `FLOAT_COLOR`/`BYTE_COLOR` on `POINT`/`CORNER`, in the same
   order.
4. `AttributeGroupMesh.new(name, type, domain)`: `type`/`domain` outside the dump's items →
   `PropertyTypeError` with `f'enum "{v}" not found in ('`; `type` `FLOAT4`/`STRING` →
   `NotImplementedInQuartz("AttributeGroupMesh.new", f"data type {type}")`; domain
   `CURVE`/`INSTANCE`/`LAYER` → `PropertyValueError` with `"domain not supported"` (Blender raises
   `RuntimeError`; class divergence **[I]**); existing name → `AttributeStore.unique_name`
   **[I]**. Order of checks: `type`, `domain` (enum), unsupported type, unsupported domain,
   color filter. In `color_attributes`, a non-color type or domain → `PropertyValueError`
   with `"color attribute"` **[I]**; the first color attribute created (through either group)
   becomes `active_color` and render color if those entries are `None` **[I]**. The data is born
   with `default_fill` (§1.5.1). Stamps `"GEOMETRY"`; returns the `Attribute`.
5. `remove(attribute)`: not an `Attribute` → `PropertyTypeError` with `"expected a Attribute type"`;
   attribute from another mesh or already removed → `PropertyValueError` with `"not found"`; required
   (`REQUIRED_ATTRIBUTES`) → `PropertyValueError` with `"is required and can't be removed"` **[I]**;
   otherwise removes from the store, invalidates the proxy (item 7), normalizes `_q_layers` and stamps `"GEOMETRY"`.
   In `color_attributes`, a non-color attribute → `"not found"`.
6. `domain_size(domain)` = `geo.domain_size(domain)`; `CURVE`/`INSTANCE`/`LAYER` → 0 **[I]**;
   invalid enum → `'enum "'`. The two groups (`attributes` and `color_attributes`) read and write the
   same `_q_layers` (`mesh.attributes.active_color is mesh.color_attributes.active_color`).
   `active`/`active_index` ↔ `_q_layers["attr_active"]`; `active_color`/`active_color_index`/
   `active_color_name` ↔ `"color_active"`; `render_color_index`/`default_color_name` ↔
   `"color_render"`. Indices: `active_index` = position in the iteration of **this** group;
   `active_color_index`/`render_color_index` = position in the iteration of `color_attributes`; with no
   entry → −1 on read (the names read `""`). Writing an index outside `[0, n)` (including −1) →
   entry `None`; writing a name that is not a color attribute → entry `None` **[I]**.
   `active`/`active_color` accept an `Attribute` of this mesh (alive) or `None` (anything else →
   `PropertyValueError` with `"not found"`; `active_color` with a non-color attribute → `"color
   attribute"`).
7. **Lifetime of layer proxies**: an `Attribute` (and a `MeshUVLoopLayer`) holds the reference to the
   `AttributeArray` (`_q_attr`) and is alive while `mesh.q_geometry.attributes.get(_q_attr.name) is
   _q_attr`. The per-name cache returns the stored proxy if alive, otherwise creates another. A dead proxy (removed,
   or geometry replaced by `from_pydata`/`clear_geometry`/`q_set_geometry`/`_q_state_set`) →
   every prop, `data` and `q_array()` raise `RemovedStructError` with `"StructRNA of type Attribute
   has been removed"` (`MeshUVLoopLayer` for UV layers) **[I]**. `q_array()` returns
   `_q_attr.data` on each call (the view is valid until the next size change of the domain).
   `Attribute.name =`: required → `PropertyValueError` with `"required"`; name already used →
   `unique_name` **[I]**; renames in the store (`AttributeStore.rename`), moves the cache key,
   updates the proxy path (`_q_set_owner(mesh, f'attributes["{new}"]')`; UV:
   `f'uv_layers["{new}"]'`) and the `_q_layers` entries holding the old name. Divergence: `type(attr)` is always
   `Attribute` (Blender uses subtypes such as `FloatVectorAttribute`).
8. `ByteColorAttributeValue`: `color` = sRGB→linear conversion of `byte/255`; `color_srgb` =
   `byte/255`; writing clamps to [0, 1] and rounds to the byte. `FloatColorAttributeValue`: `color`
   stored linear; `color_srgb` = linear→sRGB conversion (standard per-channel sRGB curve, alpha
   untouched) **[I]**.
9. `uv_layers` = non-internal `CORNER`/`FLOAT2` attributes, in store order (factory: `UVMap`
   **[O]**). `new(name="UVMap", do_init=True)`: if there are already 8 maps → returns `None` **[I]**; name
   `unique_name`; `do_init` copies the active map if there is one, otherwise zeros; the first map becomes active and
   render **[I]**. `remove(layer)`: from another mesh → `PropertyValueError` with `"not found"`;
   also removes `.pn.<name>`; a removed active one moves to the first remaining (normalization).
   `active_index`/`active_render_index` = position in `uv_layers` (−1 with no maps); writing outside
   `[0, n)` is ignored **[I]**; `active`/`active_render` accept a `MeshUVLoopLayer` of this mesh
   (anything else or `None` → `PropertyValueError` with `"not found"`). `MeshUVLoopLayer.name` renames the
   attribute (and the `.pn.`); `active = True`/`active_render = True` makes it active/render (`False` is
   ignored) **[I]**; `active_clone` reads `False` and writing is ignored **[I]**. `pin_ensure()`
   creates `.pn.<name>` with `False` if missing (stamps `"GEOMETRY"`) and returns its `Attribute`.
10. `MeshVertex.groups` is always empty; `undeformed_co == co`; `MeshLoop.tangent/bitangent` zeros
    (`calc_tangents` is NI).
11. `AttributeGroupMesh` is a collection **and** an RNA struct (`@builtin_struct` over `PropCollection`, so
    that §2.4 compares its props): `__init__(self, mesh, *, colors_only: bool)` calls
    `PropCollection.__init__(self, owner=mesh, path="color_attributes" if colors_only else
    "attributes")`, creates `_p = {}` and `_p_set = set()` (used by §1.6.4) and defines `_q_on_change(pdef)` →
    `mesh.q_tag(pdef.meta.get("dirty", "DATA"))`. `active`/`active_color` are Python properties
    because a `PointerProperty` to a non-ID struct is read-only in §1.6.4.

**`BlendDataMeshes`:** `new(name)` → `Mesh` with no geometry, 0 users **[O]**.
`new_from_object(object, preserve_all_data_layers=False, depsgraph=None)`: if `object.data` is not a
`Mesh` (including `None`) → `PropertyValueError` with `"does not have geometry data"` (Blender
raises `RuntimeError`; class divergence **[I]**); `object.mode == "EDIT"` →
`object.data.q_flush_edit()` first; new mesh (via `self.new(object.name)`, name `.NNN` if needed
**[I]**, 0 users) with a copy of the geometry, the materials and `_q_layers` (modifiers are not
evaluated; `preserve_all_data_layers` and `depsgraph` are ignored). `remove(mesh)` also removes the
objects that use it **[O]** (`probes.id_semantics.remove_used_mesh`; `DELETE_OWNER` cascade of §2.1.4).

Verified errors: `PropertyValueError` (`"sequence size mismatch"`, `"loop_total"`, `"count"`,
`"4x4"`, `"is required and can't be removed"`, `"required"`, `"not found"`, `"domain not
supported"`, `"color attribute"`, `"does not have geometry data"`), `PropertyTypeError`
(`"MeshGeometry"`, `"expected a Material type, not"`, `"expected a Attribute type"`, `'enum "'`),
`ReadOnlyError` (`"is read-only"`), `NotImplementedInQuartz` (`"Mesh.calc_tangents is not
implemented in Quartz"`, `"AttributeGroupMesh.new is not implemented in Quartz: data type FLOAT4"`),
`RemovedStructError` (`"StructRNA of type Mesh has been removed"` **[O]**, `"StructRNA of type
Attribute has been removed"` **[I]**), `IndexError` (`"out of range"`), `AttributeError` (`"has no
attribute"`).

#### 2.3.2 `quartz/types/material.py`

```python
@builtin_struct
class Material(ID):
    # PropertyDef (rule 2): all scalar/array props of id_types["Material"], dirty meta "SHADING";
    #   is_grease_pencil: BoolProperty stored with meta readonly=True (read-only through the API)
    # diffuse_color (COLOR 4 -> PropArray), specular_color (COLOR 3 -> Color with wrap_array installed), line_color (COLOR 4)
    node_tree: None                    # python ro; always None (nodes deferred)
    animation_data: None               # python ro; always None
    def inline_shader_nodes(self, *a, **k) -> NoReturn   # NI "Material.inline_shader_nodes" (python member of the dump)
    # absent: grease_pencil, lineart, cycles, texture_paint_images, texture_paint_slots
class BlendDataMaterials(IDCollection):
    def new(self, name: str) -> Material
    def create_gpencil_data(self, material: Material) -> NoReturn   # NI f"{settings.api_prefix}.data.materials.create_gpencil_data"
    def remove_gpencil_data(self, material: Material) -> NoReturn   # NI same
    def remove(self, material: Material, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None
# end: register_id_type(Material, id_type="MATERIAL", collection="materials", default_name="Material", collection_cls=BlendDataMaterials)
```

1. Defaults from the dump **[O]**: `diffuse_color (0.8, 0.8, 0.8, 1.0)` (float32), `roughness 0.4`,
   `metallic 0.0`, `specular_intensity 0.5`, `blend_method "OPAQUE"`, `surface_render_method
   "DITHERED"`, `alpha_threshold 0.5`, `pass_index 0` (0..32767).
2. `is_grease_pencil` does not accept writes through the API (`ReadOnlyError` of §1.6.4); whoever
   builds data (`l2-runtime` factory, material `"Dots Stroke"`) writes it with
   `quartz.rna.get_property(Material, "is_grease_pencil").write_raw(mat, True)` (this also applies to
   the state).
3. No references of its own (`_q_refs` = inherited) and no state keys of its own. Removing a
   material used by a mesh leaves the slot `None` (§2.1.4).

Verified errors: `ReadOnlyError` (`'attribute "is_grease_pencil" from "Material" is read-only'`),
`NotImplementedInQuartz` (`"data.materials.create_gpencil_data is not implemented in Quartz"`).

#### 2.3.3 `quartz/types/camera.py`

```python
@builtin_struct
class Camera(ID):
    # PropertyDef (rule 2): all scalar/array props of id_types["Camera"]; virt rw: angle, angle_x, angle_y
    dof: "CameraDOFSettings"           # PointerProperty(type=CameraDOFSettings, meta readonly=True): lazy instance (§1.6.4)
    animation_data: None               # python ro; always None
    # absent: stereo, custom_shader, background_images, cycles_custom
    def view_frame(self, scene: "Scene | None" = None) -> tuple[Vector, Vector, Vector, Vector]
@builtin_struct
class CameraDOFSettings(Struct):
    # PropertyDef: all scalars of sub_structs["CameraDOFSettings"] +
    focus_object: "Object | None"      # PointerProperty(type=Object, meta={"counts_user": False}) [I]
class BlendDataCameras(IDCollection):
    def new(self, name: str) -> Camera
    def remove(self, camera: Camera, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None
# end: register_id_type(Camera, id_type="CAMERA", collection="cameras", default_name="Camera", collection_cls=BlendDataCameras)
#      register_object_data_type(Camera, "CAMERA")
```

1. Defaults from the dump **[O]**: `type "PERSP"`, `lens 50`, `sensor_width 36`, `sensor_height 24`,
   `sensor_fit "AUTO"`, `clip_start 0.1` (float32 `0.10000000149011612`), `clip_end 1000`,
   `ortho_scale 6`, `display_size 1`, `lens_unit "MILLIMETERS"`.
2. Angles (virtual, computed in float64) **[I]**: `s = sensor_height` if `sensor_fit ==
   "VERTICAL"`, otherwise `sensor_width`; `angle = 2·atan(s / (2·lens))`; `angle_x` uses `sensor_width`,
   `angle_y` uses `sensor_height`. Write: `lens = s / (2·tan(a/2))` with the corresponding sensor
   (clamped to the limits of `lens`). With the defaults, `angle ≈ 0.691150` (= dump default).
3. `view_frame(scene=None)` **[I]** (computed in float64; does not depend on `display_size` or on the
   object transform): `scene` is read by *duck typing*, only `scene.render.resolution_x`,
   `resolution_y` and, via `getattr(..., 1.0)`, `pixel_aspect_x`/`pixel_aspect_y`; no import of
   `quartz.types.scene`. Aspect `(ax, ay)` = `(1, 1)` without a scene; with a scene, `rx = resolution_x ·
   pixel_aspect_x`, `ry = resolution_y · pixel_aspect_y` and the effective fit is `HORIZONTAL` if
   `sensor_fit == "HORIZONTAL"` or (`"AUTO"` and `rx ≥ ry`), otherwise `VERTICAL`; `HORIZONTAL` →
   `(1, ry/rx)`, `VERTICAL` → `(rx/ry, 1)`. `PERSP`/`PANO`/`CUSTOM`: base size `h = 0.5`,
   `s` = `sensor_height` if `sensor_fit == "VERTICAL"`, otherwise `sensor_width` (the camera's `sensor_fit`,
   not the effective one); depth `z = −h · lens / (s/2)`; half-widths `(h·ax, h·ay)`;
   offset `(shift_x·2h, shift_y·2h)`. `ORTHO`: half-widths `(ortho_scale/2·ax,
   ortho_scale/2·ay)`, offset `(shift_x·ortho_scale, shift_y·ortho_scale)`, `z = −1`. Returns
   four 3-component `Vector`s in the order top-right, bottom-right, bottom-left,
   top-left: `(hx + dx, hy + dy, z)`, `(hx + dx, −hy + dy, z)`, `(−hx + dx, −hy + dy, z)`,
   `(−hx + dx, hy + dy, z)`. Defaults without a scene → `(0.5, 0.5, −1.388889)`, `(0.5, −0.5, …)`,
   `(−0.5, −0.5, …)`, `(−0.5, 0.5, …)`; 1920×1080 scene → `(±0.5, ±0.28125, −1.388889)`; `ORTHO` with
   the defaults and no scene → `(±3, ±3, −1)`.
4. `dof` is created on first read with owner = the camera and path `"dof"` (`id_data` = camera;
   writing to `dof.*` stamps `"DATA"` on the camera). `_q_refs()` = `super()._q_refs()` + the ref of
   `dof.focus_object` (`kind "POINTER"`, `counts_user False`, `on_remove "CLEAR"`, §2.1.4) **only
   if** the generic traversal has not already emitted it (no ref with `owner is dof`); no duplicates.
5. State: generic only (`dof` is included as a nested struct, §1.6.7).

Verified errors: `PropertyTypeError` (`"expected a Object type, not Mesh"` when assigning a mesh to
`dof.focus_object`, §1.6.4).

#### 2.3.4 `quartz/types/light.py`

```python
LIGHT_TYPES: tuple[str, ...] = ("POINT", "SUN", "SPOT", "AREA")      # [O] items of Light.type
@builtin_struct
class Light(ID):
    _q_light_type: ClassVar[str] = "POINT"
    type: str      # EnumProperty(items=LIGHT_TYPES, default "POINT", meta virt): get = type(self)._q_light_type;
                   # set = swaps __class__ to the item's subclass, keeping _p/_p_set/idprops
    # PropertyDef (rule 2): remaining scalar/array props of id_types["Light"], except temperature_color (not declared); dirty "SHADING"
    node_tree: None                                  # python ro; always None
    animation_data: None                             # python ro; always None
    def area(self, matrix_world=None) -> float       # [I]
    def inline_shader_nodes(self, *a, **k) -> NoReturn   # NI "Light.inline_shader_nodes" (python member of the dump)
    # absent: cycles
@builtin_struct
class PointLight(Light): ...   # _q_light_type "POINT"; props of id_types["PointLight"] (energy, shadow_soft_size, use_soft_falloff, ...)
@builtin_struct
class SunLight(Light): ...     # "SUN"; props of id_types["SunLight"] (energy, angle, shadow_soft_size, shadow_cascade_*, ...)
@builtin_struct
class SpotLight(Light): ...    # "SPOT"; props of id_types["SpotLight"] (energy, spot_size, spot_blend, show_cone, use_square, ...)
@builtin_struct
class AreaLight(Light): ...    # "AREA"; props of id_types["AreaLight"] (energy, shape, size, size_y, spread, ...)
class BlendDataLights(IDCollection):
    def new(self, name: str, type: str) -> Light     # instance of the subclass for type
    def remove(self, light: Light, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None
# end: register_id_type(Light, id_type="LIGHT", collection="lights", default_name="Light", collection_cls=BlendDataLights)
#      register_object_data_type(Light, "LIGHT")
```

1. Internal `LIGHT_CLASSES`: item → subclass. `Light._q_construct(name)` (the base) returns a
   `PointLight` **[I]**; each subclass constructs its own class (`copy()` preserves the subclass).
2. `lights.new(name, type)`: `type` outside `LIGHT_TYPES` → `PropertyTypeError` with `'enum "{v}"
   not found in ('` and nothing is created; otherwise `IDCollection.new` and swap to the subclass. Defaults from the
   dump **[O]**: `energy 10.0` (`light.swap.energy`), `color (1, 1, 1)`, `use_shadow True`,
   `SunLight.angle ≈ 0.009180`, `SpotLight.spot_size ≈ 0.785398`, `spot_blend 0.15`,
   `AreaLight.size 0.25`, `shape "SQUARE"`; `shadow_soft_size` starts with the dump default (0.0)
   **[I]**.
3. **Type swap** (divergence 4 of ARCHITECTURE §13): `light.type = "SUN"` swaps `__class__` of the
   existing instance to `SunLight` (Blender keeps `PointLight` in the live reference:
   `light.swap.cls_after == "PointLight"`, `has_angle False` **[O]**; in Quartz `type(l) is
   SunLight` and `hasattr(l, "angle")`). Values in `_p` survive: `energy` stays 10.0 **[O]**
   (`energy_after`); props with no owner in the new class stay stored and reappear when going back to the type
   **[I]**. Writing the current type swaps nothing but follows §1.6.4 (stamps, notifies, `update`).
   The tombstone of a removed light uses the RNA name of the subclass (`"StructRNA of type SunLight has been
   removed"` **[I]**).
4. `area(matrix_world=None)` **[I]**: `matrix_world` (`Matrix` or 4×4; `None` = identity); `sx,
   sy, sz` = lengths of the first three columns of the 3×3 part. `AREA`: `SQUARE size²`,
   `RECTANGLE size·size_y`, `DISK π·(size/2)²`, `ELLIPSE π·size·size_y/4`, times `sx·sy`;
   `POINT`/`SPOT`: `4π·r²` with `r = shadow_soft_size · (sx+sy+sz)/3`; `SUN`: `π·tan(angle/2)²`.
5. State: key `"light_type"` (`str`); `_q_state_set` swaps the class before restoring the generic state.

Verified errors: `PropertyTypeError` (`'enum "BAD" not found in ('`), `AttributeError`
(`"has no attribute 'angle'"` on a `PointLight`, strict class).

#### 2.3.5 `quartz/types/image.py`

```python
@builtin_struct
class Image(ID):
    # PropertyDef (rule 2): all scalar/array props of id_types["Image"]; virt ro: type ("IMAGE"), size (INT 2),
    #   depth, channels, is_float, has_data, is_dirty, frame_duration (0), is_stereo_3d (False), is_multiview (False)
    pixels: PropArray      # python (dynamic size; exception to rule 2): live float32 view of length w*h*4; assignment copies
    packed_file: None      # python ro
    # absent: packed_files, render_slots, tiles, colorspace_settings, stereo_3d_format
    def scale(self, width: int, height: int, frame: int = 0, tile_index: int = 0) -> None
    def reload(self) -> None
    def update(self) -> None                          # q_tag("DATA")
    def filepath_from_user(self, image_user: object = None) -> str    # filepath
    def gl_free(self) -> None; def buffers_free(self) -> None         # no-op
    def gl_touch(self, *a, **k) -> NoReturn; def gl_load(self, *a, **k) -> NoReturn   # NI
    def save(self, *a, **k) -> NoReturn; def save_render(self, *a, **k) -> NoReturn
    def pack(self, *a, **k) -> NoReturn; def unpack(self, *a, **k) -> NoReturn         # NI ("Image.save", ...)
class BlendDataImages(IDCollection):
    def new(self, name: str, width: int, height: int, alpha: bool = False, float_buffer: bool = False,
            stereo3d: bool = False, is_data: bool = False, tiled: bool = False) -> Image
    def load(self, filepath: str, check_existing: bool = False) -> Image
    def remove(self, image: Image, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None
# end: register_id_type(Image, id_type="IMAGE", collection="images", default_name="Image", collection_cls=BlendDataImages)
```

1. Internal storage: `_q_size = (w, h)`, `_q_pixels: np.ndarray | None` (float32, `(h·w·4,)`,
   interleaved RGBA, row 0 = bottom row), `_q_float`, `_q_alpha`, `_q_is_dirty` (name distinct
   from the storage of `ID.q_dirty`, §2.2.3).
   `channels = 4` with a buffer, otherwise 0; `depth` = 32/24 (bytes with/without alpha) or 128/96 (float with/without
   alpha), 0 without a buffer; `has_data` = buffer present **[I]**.
2. `images.new(...)`: `width`/`height` outside [1, 65536] → `PropertyValueError` with `"not in
   range"` **[I]**; `source = "TILED"` if `tiled`, otherwise `"GENERATED"`; `generated_type "BLANK"`,
   `generated_width/height` = width/height, `generated_color (0, 0, 0, 1)`, `use_generated_float =
   float_buffer`; buffer filled with `generated_color`; `is_dirty False` **[I]**. `stereo3d` and
   `is_data` are accepted with no effect.
3. `GENERATED` image: writing `generated_width/height/color/type/use_generated_float` recreates the
   buffer (every generated type is filled with the solid color, with no UV grid, divergence **[I]**).
4. `pixels`: read → `PropArray(self._q_pixels, on_write=…, owner=self)` (without a buffer:
   `PropArray` over `np.zeros(0, np.float32)`); writing by index or slice marks `is_dirty` and
   stamps `"DATA"`; a byte image (`not is_float`) is clamped to [0, 1] and quantized in steps of
   1/255 after each write **[I]**. `image.pixels = seq` (iterable or ndarray, flattened) with size ≠
   `w·h·4` → `PropertyValueError` with `f"should contain {n} items, not {m}"`; otherwise copies into
   `_q_pixels` (same memory: `PropArray`s already returned stay alive), same marking and stamp.
   Without a buffer, only an empty `seq` is accepted (no-op).
5. `images.load(filepath, check_existing=False)`: neither reads nor checks the file (divergence **[I]**;
   Blender decodes it and fails on a missing file); name = `quartz.path.basename(filepath)`
   (unique in the collection); `filepath = filepath_raw = filepath`; `source "FILE"`; `file_format` by
   extension (`.png PNG`, `.jpg/.jpeg JPEG`, `.exr OPEN_EXR`, `.hdr HDR`, `.tga TARGA`, `.tif/.tiff
   TIFF`, `.bmp BMP`, `.webp WEBP`, others: dump default) **[I]**; no buffer (`has_data False`,
   `size (0, 0)`). `check_existing=True` with an image whose `filepath` has the same
   `os.path.normcase(os.path.abspath(...))` → returns the existing one.
6. `scale(w, h, ...)`: no buffer → `PropertyValueError` with `"does not have any image data"` (Blender
   raises `RuntimeError`; class divergence **[I]**); dimensions outside [1, 65536] →
   `PropertyValueError` with `"not in range"`; `frame`/`tile_index` ignored; nearest-neighbor resampling
   **[I]**; `size` changes, `generated_*` does not; `is_dirty True`. `reload()`: `GENERATED` recreates the buffer;
   `FILE` changes nothing; `is_dirty False`.
7. State: key `"image_buffer"` = `{"size": (w, h), "pixels": ndarray | None, "is_float": bool,
   "alpha": bool, "dirty": bool}`.

Verified errors: `PropertyValueError` (`"not in range"`, `"should contain"`, `"does not have any
image data"`), `NotImplementedInQuartz` (`"Image.save is not implemented in Quartz"`).

#### 2.3.6 `quartz/types/text.py`

```python
@builtin_struct
class Text(ID):
    # PropertyDef (rule 2): all scalars of id_types["Text"]; virt ro: is_dirty, is_modified (False), is_in_memory;
    #   virt rw: current_line_index, current_character, select_end_line_index, select_end_character (clamped)
    lines: PropCollection                 # python; items TextLine (owner = text, path f"lines[{i}]")
    current_line: "TextLine"              # python ro: cursor line
    select_end_line: "TextLine"           # python ro
    def clear(self) -> None
    def write(self, text: str) -> None
    def from_string(self, text: str) -> None
    def as_string(self) -> str
    def is_syntax_highlight_supported(self) -> bool
    def select_set(self, line_start: int, char_start: int, line_end: int, char_end: int) -> None
    def cursor_set(self, line: int, character: int = 0, select: bool = False) -> None
    def as_module(self) -> ModuleType
    def region_as_string(self, *a, **k) -> str      # accepts range=((l0, c0), (l1, c1)) or None (selection) [I]
    def region_from_string(self, *a, **k) -> None   # (body, range=None) [I]
@builtin_struct
class TextLine(Struct):                   # body (STRING, virt rw)
class BlendDataTexts(IDCollection):
    def new(self, name: str) -> Text
    def load(self, filepath: str, internal: bool = False) -> Text
    def remove(self, text: Text, do_unlink: bool = True, do_id_user: bool = True, do_ui_user: bool = True) -> None
# end: register_id_type(Text, id_type="TEXT", collection="texts", default_name="Text", collection_cls=BlendDataTexts)
```

1. Storage: `_q_lines: list[str]` (always ≥ 1 line; empty text = `[""]`), `_q_cursor = [line,
   character, selection_end_line, selection_end_character]`, `_q_in_memory`, `_q_is_dirty` (name
   distinct from the storage of `ID.q_dirty`). New lines normalized: `"\r\n"` and `"\r"` become
   `"\n"` **[I]**.
2. `as_string()` = `"\n".join(lines)`. `from_string(t)`: replaces everything; cursor and selection end at the
   end of the text. `write(t)`: inserts at the cursor position replacing the selection; cursor after the text
   inserted. `clear()`: `[""]`, cursor `(0, 0)`. Every edit sets `is_dirty` and stamps `"DATA"`
   **[I]**.
3. Cursor: writing to `current_line_index`/`select_end_line_index` clamps to `[0, number of lines −
   1]`; characters to `[0, len(line)]`. `cursor_set(line, character, select)`: positions the cursor;
   `select=False` collapses the selection onto the cursor. `select_set(l0, c0, l1, c1)`: cursor at `(l0, c0)`,
   end at `(l1, c1)`, both clamped **[I]**.
4. `TextLine.body =` replaces the line; `"\n"` in the value splits it into several **[I]**.
   `region_as_string(range=None)` (one positional or the keyword `range`; any other argument →
   `TypeError`): `range` = `((l0, c0), (l1, c1))` with the pairs ordered and clamped like the cursor;
   `None` = the selection (cursor → selection end, in order); returns the span with `"\n"` between lines.
   `region_from_string(body, range=None)`: replaces the same span with `body` (normalized), cursor
   and selection end at the end of the inserted text, sets `is_dirty`, stamps `"DATA"` **[I]**.
5. `is_syntax_highlight_supported()` → name extension in `{".py", ".osl", ".glsl", ".toml"}`
   **[I]**. `as_module()`: `ModuleType(name without ".py")`, `__file__` = name of the text, runs
   `compile(as_string(), name, "exec")` in the module dictionary and returns it, without inserting into
   `sys.modules` **[I]**; errors in the code propagate.
6. `texts.new(name)`: `is_in_memory True`, `is_dirty False`. `texts.load(filepath, internal=False)`:
   reads with `encoding="utf-8", errors="replace"` (missing file → Python's `OSError` propagates);
   name = `os.path.basename(filepath)` (unique); `filepath` = the given path, or `""` with `internal`;
   `is_in_memory = internal`; `is_dirty False`; cursor `(0, 0)`.
7. State: key `"text_body"` = `{"lines": list[str], "cursor": [4 ints], "in_memory": bool,
   "dirty": bool}`.

Verified errors: `FileNotFoundError` in `texts.load` of a nonexistent path; `ReadOnlyError`
(`'attribute "is_dirty" from "Text" is read-only'`).

#### 2.3.7 Tests

The seven files run **without** `quartz.session` and without `quartz.testing` (except
`test_datablock_schema.py`, §2.4). There is no `conftest.py` for this task: each file defines its own
local fixtures: `l2_env` (`hooks.snapshot()`, `msgbus.snapshot()`, `settings.snapshot()`,
`quartz.types.install_hooks()`; on exit, in `finally`: `set_editmode_hooks()`,
`settings.restore`, `msgbus.restore`, `hooks.restore`) and `bd` (a new `BlendData()`, depends on
`l2_env`). Tests that only need a loose ID use `Mesh._q_construct("M")` (no `BlendData`);
those that need `repr` install `hooks.install(repr_root=lambda: "bpy")` inside the snapshot/restore
pair. Test meshes come from `from_pydata` or from `q_set_geometry(quartz.geometry.cube())`
(and the other primitives of §1.5.4). Scenes for `view_frame` are fake
(`types.SimpleNamespace(render=SimpleNamespace(resolution_x=..., resolution_y=...))`), without
`quartz.types.scene`. **[O]** facts are read from the `blender_facts`/`blender_dump` fixtures (§1.1.2),
not copied by hand. They depend on `quartz.types.id`/`blenddata`/`object` (§0.6): they pass the L2 gate.

- `tests/unit/types/test_mesh_api.py`: `meshes.new` (0 users **[O]**; names `.001`/`.002`
  **[O]** `dup_names`); `from_pydata` with the facts from `probes.id_semantics` (counts, `validate()
  False`, attributes as a set, `polygons[0]`, `edge_keys` as a set) **[O]**; `shade_flat`
  and `mesh.shade` **[O]**; `update(calc_edges=True)` and the "faces without edges" case; `clear_geometry`;
  `transform` (and `"4x4"`); `flip_normals`/`flip`; `shade_flat/shade_smooth`;
  `set_sharp_from_angle` on a cube (12 sharp edges at 30°, none at 100°); `split_faces` on a flat
  cube (24 vertices); `loop_triangles` of a quad (2 triangles, `polygon_index` 0) and of a cube
  (12); `normals_domain`; face normals and `center`/`area`; `count_selected_items`; proxies
  (equality without identity, equal `hash` for equal proxies, `v in mesh.vertices` true,
  `index`, `IndexError` on creation and after the domain shrinks, writing `v.co.x = 1` stamps
  `"GEOMETRY"`, `select` stamps `"SELECT"`, `hide` stamps `"VISIBILITY"`); `repr` of mesh,
  vertex **[O]** (`repr.mesh`, `repr.vertex`) and collection; `MeshPolygon.vertices` (`"loop_total"`);
  `add(count)` (and `"count"`) and the low-level flow equal to `from_pydata`; `materials`
  (`append`/`pop`/`clear`/`__setitem__`, users 0 → 1 **[O]**, `pop` adjusts `material_index`,
  `clear` zeroes `material_index`, `"expected a Material type, not"`, removed material →
  `RemovedStructError`, `IndexError` with `"out of range"`); removing the material leaves the slot `None`;
  `meshes.remove` removes the object that uses it and later access raises `"StructRNA of type Mesh has
  been removed"` **[O]**; `copy()` copies the geometry (independent arrays) and shares materials;
  `q_set_geometry` (adoption without copy, `"MeshGeometry"`, `UVMap` becomes active and render by
  normalization); `q_bounds` (empty → zeros); edit mode with fake hooks (`enter` called once,
  `is_editmode`, `flush` only with `q_edit_data`, stamp only on exit, `q_flush_edit` True/False,
  `enter` that raises undoes the state, `flush` that raises keeps the edit, requesting the current state is
  a no-op, default without L3); `new_from_object` (empty object → `"does not have geometry data"`; independent
  copy; name `.NNN`); `_q_state_get`/`_q_state_set` round trip (geometry, materials,
  layers, edit; old `Attribute` proxies die); NI of `calc_tangents`, `vertex_creases` and
  `vertex_colors`; `animation_data is None`.
- `tests/unit/types/test_mesh_foreach.py`: each row of the mapping table in `foreach_get`
  (list and ndarray `float32`/`float64`/`int32`/`bool`) and, for the writable ones, `foreach_set` round trip;
  `foreach_get_co` **[O]**; `polygons.foreach_get("vertices")` with size = number of corners **[O]**;
  `"sequence size mismatch"` in both directions (and nothing written); `"is read-only"` (`normal`, `index`,
  `loop_total`); `"has no attribute"` on an empty collection; `foreach_set("loop_start")` decreasing →
  `PropertyValueError`; attribute created on demand (`hide`, `use_seam`, `material_index`, `select`);
  `meshes.new` + `vertices.add(3)` → `vertices.foreach_get("select", …)` all `False` and no
  `.select_vert`; `foreach_set("select", …)` creates `.select_vert` (POINT, BOOLEAN);
  `use_smooth` ↔ inverted `sharp_face`; per-channel stamps after `foreach_set`; normal caches
  invalidated after `foreach_set("co")`; `foreach` on `Attribute.data` and `uv_layers[...].data/uv`.
- `tests/unit/types/test_mesh_attributes.py`: iteration of `attributes` with internals and key by name
  (set `(name, domain, type)` after `from_pydata` **[O]**); `new` for the 12 supported types
  (item class, shape and dtype of `q_array()`, `Vector`/`Quaternion`/`Matrix`/`PropArray` in the items
  with hooks installed); `FLOAT4`/`STRING` → NI; `CURVE` → `"domain not supported"`; invalid
  enum → `'enum "'`; repeated name → `.001`; `remove` (required → `"is required and can't be
  removed"`; foreign → `"not found"`; non-`Attribute` → `"expected a Attribute type"`; removed
  proxy → `"StructRNA of type Attribute has been removed"`; proxy dies after `from_pydata` and a
  new attribute with the same name gives a new proxy); rename (required → `"required"`; cache and
  `_q_layers` follow the new name); `domain_size`; `active`/`active_index`/`active_color` (indices
  −1 with no entry, out-of-range write → no active, `attributes.active_color is
  color_attributes.active_color`); `color_attributes` (filter, `"color attribute"`, first becomes
  active and render); `ByteColorAttributeValue.color`/`color_srgb`; stable identity of
  `Attribute` and of `MeshUVLoopLayer`; `uv_layers.new` (names, `do_init`, active/render, limit 8 →
  `None`), `remove` (active passes to the first remaining), rename (`.pn.` follows), `pin_ensure`
  (returns `Attribute` `.pn.<name>`, `CORNER`/`BOOLEAN`; second call returns the same one),
  `MeshUVLoop.uv`; stamps by attribute name (`.select_vert` → `"SELECT"`).
- `tests/unit/types/test_material_camera.py`: `Material` and `Camera` defaults from the dump **[O]**;
  `diffuse_color` 4 → `PropArray`, `specular_color` → `Color` with hooks; write stamps
  `"SHADING"` (material) and `"DATA"` (camera); `is_grease_pencil` read-only and `write_raw`;
  `create_gpencil_data` NI with `api_prefix`; `angle`/`angle_x`/`angle_y` and write of `angle`
  (round trip with `lens`); `view_frame` without a scene (`(±0.5, ±0.5, −1.388889)`), with a fake
  1920×1080 scene (`(±0.5, ±0.28125, −1.388889)`), with `sensor_fit "VERTICAL"`, with `shift_x`, and `ORTHO`
  (`(±3, ±3, −1)`), tolerance `1e-5`; `animation_data is None` and NI of
  `inline_shader_nodes`; lazy `dof` (same instance on consecutive reads, `repr`, stamp on the camera);
  `focus_object` does not count a user, rejects `Mesh` (`"expected a Object type, not Mesh"`) and becomes
  `None` when the object is removed; `Object` with camera `data` has `type "CAMERA"`; state round
  trip (with `dof`).
- `tests/unit/types/test_light.py`: `lights.new` for the 4 types (exact class, `energy 10.0`
  **[O]**); invalid type (`'enum "BAD" not found in ('`, nothing created); type swap per §2.3.4
  rule 3 (new class, `energy` preserved **[O]**, `angle` accessible only as `SunLight`, orphan
  value reappears when going back); strict `AttributeError` on `PointLight.angle`; `copy()` preserves the
  subclass; `area()` of the four types with and without a scaled `matrix_world` (e.g. default `AREA` `SQUARE`
  → `0.0625`, with uniform scale 2 → `0.25`; `POINT` with `shadow_soft_size 0.1` →
  `0.1256637`; `shadow_soft_size 0` → `0`), tolerance `1e-6`; `Object` with a light has
  `type "LIGHT"`; state round trip swaps the class; tombstone with the subclass name.
- `tests/unit/types/test_image_text.py`: `images.new` (size, `channels`, `depth` in the four
  combinations, `has_data`, pixels filled with `(0, 0, 0, 1)`, `"not in range"`); `pixels`
  (length `w·h·4`, write by slice, byte quantization, `is_dirty`, `"should contain"`);
  `scale` (and `"does not have any image data"` on a loaded image); `reload`; regeneration when changing
  `generated_width`; `images.load` (name from the file, `has_data False`, `file_format` by extension,
  `check_existing`); NI of `save`; state round trip. `Text`: `new`, `write`/`from_string`/
  `as_string`/`clear`, line-break normalization, cursor and selection (clamping), `lines`/
  `current_line`/`TextLine.body` (including splitting by `"\n"`), `is_in_memory`, `is_dirty` read-only,
  `region_as_string`/`region_from_string`, `as_module` (function defined in the text is
  callable; `SyntaxError` propagates), `is_syntax_highlight_supported`, `texts.load` of a file in
  `tmp_path` (UTF-8, `internal`) and of a missing path (`FileNotFoundError`); state round trip.
- `tests/unit/types/test_datablock_schema.py` (§2.4; uses `quartz.testing` and `blender_dump`; passes the
  gate): module-level `DIVERGENCES`; `rna_schema_diff(cls, props)` empty for `Mesh`, `Material`,
  `Camera`, `Light`, `PointLight`, `SunLight`, `SpotLight`, `AreaLight`, `Image`, `Text`
  (`id_types`) and `MeshVertex`, `MeshEdge`, `MeshLoop`, `MeshPolygon`, `MeshLoopTriangle`,
  `MeshUVLoopLayer`, `Attribute`, `AttributeGroupMesh`, `CameraDOFSettings` (`sub_structs`);
  `function_signature_diff` empty for the implemented RNA functions (`Mesh.transform`,
  `flip_normals`, `set_sharp_from_angle`, `split_faces`, `calc_loop_triangles`, `update`,
  `update_gpu_tag`, `free_tangents`, `clear_geometry`, `validate`, `validate_material_indices`,
  `count_selected_items`; `MeshPolygon.flip`; `Camera.view_frame`; `Light.area`; `Image.scale`,
  `reload`, `update`, `gl_free`, `buffers_free`, `filepath_from_user`; the 7 functions of `Text`;
  `MeshUVLoopLayer.pin_ensure`) and for `new`/`remove` (+ `new_from_object`, `images.load`,
  `texts.load`) of the six collections (`data.collections[...]["functions"]`) and for `add`,
  `AttributeGroupMesh.new/remove/domain_size`, `UVLoopLayers.new/remove`,
  `IDMaterials.append/pop/clear` (`collection_api` of the `Mesh` props); the declaration rule
  (§2.3, rule 2) checked with `require_all=True` over the scalar subset of the dump (entries of
  type `BOOLEAN`/`INT`/`FLOAT`/`STRING`/`ENUM`) minus the exceptions in this section: exactly
  `MeshPolygon.vertices`, `Image.pixels` and `Light.temperature_color` (keys of `DIVERGENCES` with
  a reason); `__all__` of each module with no names repeated across modules.

### 2.4 Schema conformance with the dump

The built-in types and built-in operators declare properties with name, type, subtype, unit,
size, default, limits and items from Blender 5.2.2 (D3; ARCHITECTURE §11, item 3). This section fixes
how this is verified, without running Blender; each task applies the rules in its own tests, with
the helpers from `quartz.testing` (§2.6.8). Schema tests may depend on `quartz.testing` and
pass the L2 gate (§0.6).

#### 2.4.1 Sources in the dump

The tests read the dump through the `blender_dump` fixture (§1.1.2).

| What | Key in `data/blender_api_dump.json` |
|---|---|
| ID props (`ID`, `Object`, `Mesh`, `Scene`, `Collection`, `Material`, `Camera`, `Light` and subtypes, `World`, `Image`, `Text`) | `id_types[<RNA name>]["properties"]` |
| struct props (`MeshVertex`, `MeshEdge`, `MeshPolygon`, `MeshLoop`, `MeshLoopTriangle`, `MeshUVLoopLayer`, `Attribute`, `AttributeGroupMesh`, `MaterialSlot`, `ViewLayer`, `LayerCollection`, `RenderSettings`, `Modifier`, `CameraDOFSettings`, `ToolSettings`, `UnitSettings`, `View3DCursor`, `BlendData`, `Context`, `WindowManager`, `Preferences`, `Addon`, `Event`, `KeyMap`, `KeyMapItem`, `OperatorProperties`, `Depsgraph`, `DepsgraphUpdate`) | `sub_structs[<RNA name>]["properties"]` |
| props and callbacks of the registrable bases | `base_classes[<base>]` (`properties`, `functions`, `registration`) |
| RNA functions (signatures) | `["functions"]` of the entries above; `data.collections[<attr>]["functions"]`; `["collection_api"]["functions"]` of `COLLECTION` props |
| operator props and `bl_options` | `ops.submodules[<mod>][<op>]` (`props`, `bl_options`) |
| context members | `context` (without the `{"kind": "method"}` entries) |

#### 2.4.2 `rna_schema_diff(cls, dump_props, *, require_all=False, divergences=None) -> list[str]`

`T` = `cls.bl_rna.identifier`.

1. `declared` = the `PropertyDef`s in `cls.__dict__` itself (the dump lists, per struct, only the
   struct's own props; those inherited from a built-in base are verified at the base's entry — e.g. those of
   `ID` in `id_types["ID"]`, those of `Light` in `id_types["Light"]`). An operator's property class
   (§2.5.2) has all its props in its own `__dict__`.
2. For each declared identifier:
   1. absent from `dump_props` and without the `q_` prefix → `f"{T}.{id}: not in dump (Quartz-only props need
      the 'q_' prefix)"` (verifies the rule of §0.2);
   2. present → compare `p.to_rna_dict()` (§1.6.4) with the dump entry in the fields `type`,
      `subtype`, `unit`, `array_length`, `array_dimensions`, `default`, `min`, `max`, `soft_min`,
      `soft_max`, `step`, `precision`, `items`, `length_max`, `fixed_type`; `flags` compared as a
      set restricted to `{"is_readonly", "is_hidden", "is_skip_save", "is_never_none",
      "is_enum_flag"}`. Floats: both sides rounded to float32 (`to_float32`) and compared with
      relative tolerance `1e-6`. Lists (array `default`, `items`): element by element, in
      order. A field present on one side and absent on the other is a difference (except `unit` absent =
      `"NONE"`).
3. `require_all=True`: each dump identifier not declared → `f"{T}.{id}: missing (declared by
   Blender)"`.
4. Each difference becomes `f"{T}.{id}.{field}: expected {dump_value!r} got {quartz_value!r}"`. A
   message is omitted if `f"{T}.{id}.{field}"` or `f"{T}.{id}"` is a key of `divergences`.
5. Returns the sorted messages; empty list = conformant.

#### 2.4.3 `function_signature_diff(func, dump_func, *, divergences=None) -> list[str]`

1. Expected: `dump_func["params"]` without those with `"output": True`, in order (`use_self` ignored).
2. Obtained: `inspect.signature(func)` without `self`/`cls`. The names MUST match in the same order;
   extra Quartz parameters only at the end, keyword-only and with a default; `"required": True` ↔ no
   default; the others ↔ with a default.
3. Messages `f"{func.__qualname__}: {problem}"`; omitted if `func.__qualname__` or
   `f"{func.__qualname__}.{parameter}"` is in `divergences`.

#### 2.4.4 What each task verifies

| Task | Classes (declared props, `require_all=False`) | Functions (`function_signature_diff`) | Where |
|---|---|---|---|
| `l2-idmodel` | `ID`, `Object`, `Collection`, `Scene`, `World`, `BlendData`, `ViewLayer`, `LayerCollection`, `RenderSettings`, `UnitSettings`, `ToolSettings`, `View3DCursor`, `WindowManager`, `KeyMap`, `KeyMapItem`, `Depsgraph`, `DepsgraphUpdate`, `MaterialSlot`, `Modifier` | `ID.rename/copy/user_remap/user_of_id/evaluated_get/update_tag/make_local`; `new`/`remove`/`tag` of the implemented collections that this task registers; `Object.select_get/select_set/hide_get/hide_set/visible_get/to_mesh/convert_space/ray_cast/closest_point_on_mesh`; `Scene.frame_set/statistics/ray_cast`; `ViewLayer.update`; `Depsgraph.update/id_eval_get/id_type_updated`; `WindowManager` (implemented functions) | files of §2.2.12 (the author says which covers which) |
| `l2-datablocks` | `Mesh`, `MeshVertex`, `MeshEdge`, `MeshLoop`, `MeshPolygon`, `MeshLoopTriangle`, `MeshUVLoopLayer`, `Attribute`, `AttributeGroupMesh`, `Material`, `Camera`, `CameraDOFSettings`, `Light`, `PointLight`, `SunLight`, `SpotLight`, `AreaLight`, `Image`, `Text` | implemented functions of these types and `new`/`new_from_object`/`load`/`remove` of their collections | `test_datablock_schema.py` |
| `l2-registry-ui` | `Operator`, `Panel`, `Menu`, `Header`, `UIList`, `PropertyGroup`, `AddonPreferences` (props of `base_classes`), `Preferences`, `Addon`, `Event`, `OperatorProperties` | callbacks of the bases: names and "classmethod yes/no" equal to `registration.callbacks` | `tests/unit/registry/*.py` |
| `l2-runtime` | `Context`: `set(CONTEXT_MEMBERS)` == dump members (71) and `CONTEXT_METHODS` == the 4 methods | — | `tests/unit/runtime/*.py` |
| `l2-operators` | each built-in operator: `rna_schema_diff(op.q_properties_class(), props, require_all=True)` and `set(bl_options)` == dump | — | `tests/unit/operators/*.py` |

#### 2.4.5 Divergences

1. Each schema test file defines a module dictionary `DIVERGENCES: dict[str, str]`
   (key `"<T>.<id>[.<field>]"` or `"<qualname>[.<parameter>]"`, value = short reason in English,
   never empty) and passes it to the helpers.
2. The schema divergence categories appear in `docs/COMPAT.md` (§3.1.7).
3. Already known: dynamic enums (`object.mode_set.mode` has items per type of the active object
   **[O]**; the dump lists the 14 static ones); computed props declare the dump default (e.g. zeros in
   `matrix_world`, `matrix_basis`, `matrix_local`, `bound_box`, `dimensions`) and compute the real value
   on read — no divergence; props that Quartz does not declare simply do not appear
   (`require_all=False`), except in the built-in operators.

### 2.5 Registration, headless UI and utils (`l2-registry-ui`)

Modules: `quartz.registry`, `quartz.types.operator`, `quartz.types.ui`, `quartz.types.prefs`,
`quartz.types.stubs`, `quartz.ui`, `quartz.utils` (+ `previews`, `units`). Uses only L1 (§0.6):
`quartz.errors`, `quartz.props`, `quartz.rna` (including `hooks`), `quartz.app` (`settings`,
`paths`, `translations`, `version`), `quartz.path`; `quartz.session` only lazily inside
`quartz.utils.blend_paths`. Internal graph: `registry` does not import any other module of the task at
module level (it imports `quartz.types.ui` inside `snapshot`/`restore`, tolerating
`ModuleNotFoundError`); `types.operator`, `types.ui`, `types.prefs`, `types.stubs` import
`registry`; `types.stubs` imports `types.operator`; `types.ui` imports `quartz.utils` only inside
`Menu.draw_preset`; `quartz.ui` imports `registry`, `types.ui` and `types.operator`; `quartz.utils`
imports `registry`. No module of the task uses names from `quartz.types` (package: `__getattr__`,
`load_builtin_types`, `set_name_resolver`, …) nor imports `quartz.types.id`/`blenddata`/`object` or
another module of `l2-idmodel`/`l2-datablocks`; the implicit import of `quartz/types/__init__.py` as
the parent package of `quartz.types.operator` etc. is accepted (it is lazy and has no effects, §2.0.1, rule 2; without
the file, `quartz.types` is a namespace package).

Common rules of the section:

1. Import effects: only those of §2.0.2 (`register_base(...)`). No hook is installed at import.
2. Each module of `BUILTIN_TYPE_MODULES` of this task (`types.operator`, `types.ui`, `types.prefs`,
   `types.stubs`, `quartz.ui`) MUST define `__all__` with all the public names listed in its
   signature block.
3. **No defaults injected into `bl_*`**: no registrable base declares `bl_idname`, `bl_label`,
   `bl_options`, … neither as an attribute nor as a `PropertyDef`; reading a `bl_*` not defined by the user's
   class raises `AttributeError` (**[O]** for `Operator`, judge `ops.defaults`: `"type object
   'QZPROBE_OT_defaults' has no attribute 'bl_translation_context'"`; **[I]** for the other bases;
   the `bl_*` that the dump lists for each base are read by the registry with `getattr`, not declared,
   and therefore do not enter §2.4). Whoever needs a default uses
   `getattr(cls, name, default)`. For the same reason the bases MUST NOT define the user callbacks
   (`poll`, `execute`, `invoke`, `modal`, `draw`, `draw_item`, …) nor `register`/`unregister`: in this
   section "the class has `X`" is `hasattr(cls, X)`. (§2.6.3 decides execution by the MRO preceding the
   base; since bases and `Struct` do not define callbacks, the two criteria only diverge for a mixin
   listed after the base, a case this section accepts.)
4. Registrable bases and user subclasses are not strict (`_q_strict_attrs = False`); the
   other types of this section (`OperatorProperties` and the classes generated per operator,
   `OperatorOptions`, `Event`, `UILayout`, `Preferences` and sub-structs, `Addon`, `UserExtensionRepo`,
   `ImagePreview`, `Space*`) are strict `@builtin_struct`s.
5. **State**: no type in this section is an ID or participates in undo/`.qz` state (§2.1.5):
   `Preferences`, `Addon`, `UILayout`, `Event`, operator instances and `Panel`/`Menu` instances are not
   saved or restored (the `.qz` does not carry preferences **[I]**). `PropertyGroup` instances
   hung on IDs use the generic `Struct` protocol (§1.6.7). The registry state has its own
   protocol (`registry.snapshot/restore`), which undo does NOT touch.
6. "Empty collection" in this section = an instance of a private subclass of `PropCollection` whose
   `_q_items()` returns `()` (created once per owner and stored: same instance on each read).
7. **[L]** in this section (and in §2.1) marks behavior deduced from reading Blender's Python modules,
   without a probe; for golden purposes it counts as **[I]**.

#### 2.5.1 `quartz/registry.py`

```python
def register_base(base: type, *, required: Sequence[str] = (), rna_name: Callable[[type], str] | None = None,
                  validate: Callable[[type], None] | None = None,
                  kind: str = "GENERIC",                                  # "OPERATOR" | "UI" | "GENERIC"
                  callbacks: Mapping[str, tuple[bool, bool]] | None = None,   # name -> (optional, classmethod) [O dump]; None = {}
                  prepare: Callable[[type, str], None] | None = None,      # step 6 of §2.1.6 (cls, RNA name)
                  cleanup: Callable[[type], None] | None = None) -> None   # called on unregister, after cls.unregister()
    # base must be a subclass of quartz.rna.Struct with "bl_rna" in its own __dict__, otherwise TypeError;
    # calling again for the same base replaces the entry (idempotent on imports)
def registrable_base_of(cls: type) -> type | None       # 1st class of cls.__mro__ (including cls) registered with register_base
def iter_bases() -> Iterator[type]                       # bases in register_base order
def base_callbacks(base: type) -> Mapping[str, tuple[bool, bool]]   # read-only view; unknown base -> KeyError
def register_class(cls: type) -> None                    # §2.1.6 + rules below [O]
def unregister_class(cls: type) -> None
def is_registered(cls: type) -> bool                     # "bl_rna" in cls.__dict__ and indexed by register_class (built-in types -> False)
def rna_name_of(cls: type) -> str                        # RNA name of a registered class; otherwise what register_class would use (without validating;
                                                         # without registrable base or idname without "." -> cls.__name__; never raises)
def lookup(rna_name: str, *, resolve: bool = True) -> type | None
def operator_class(idname: str) -> type | None           # accepts "mod.op" and "MOD_OT_op"; registered Operator and Macro
def operator_rna_name(idname: str) -> str                # "mesh.primitive_cube_add" -> "MESH_OT_primitive_cube_add" [O]; splits at the 1st "."
def operator_idname_py(rna_name: str) -> str             # inverse; without "_OT_" -> ValueError
def validate_operator_idname(idname: str, class_name: str) -> None   # RegistrationRuntimeError [O]
def iter_classes(base: type | None = None) -> Iterator[type]          # registration order; base -> issubclass(c, base)
def iter_operators() -> Iterator[tuple[str, type]]                    # (idname_py, class), registration order
def operator_submodules() -> list[str]                                # sorted(set(module of each idname_py))
def counts_by_base() -> dict[str, int]                                # base.__name__ -> count (only > 0; ignores owners "quartz.*")
@contextmanager
def owner_scope(owner: str | None) -> Iterator[None]                  # pushes; restores in finally
def current_owner() -> str | None                                     # top of the stack or None
def owner_of(cls: type) -> str | None                                 # owner recorded in the registry; not registered -> None
def classes_owned_by(owner: str) -> list[type]                        # registered with this owner, registration order
def type_props_owned_by(owner: str) -> list[tuple[type, str]]         # dynamic props defined under owner and still present
def set_missing_type_resolver(fn: Callable[[str], type | None] | None) -> None
def subscribe(callback: Callable[[str, type], None]) -> Callable[[], None]   # returns the canceller (idempotent)
def snapshot() -> object
def restore(snap: object) -> None
def install_hooks() -> None                              # hooks.install(on_type_property_defined=_on_defined, on_type_property_removed=_on_removed); idempotent
```

**Base table** (normative). Each row is registered by `register_base(...)` at the end of the indicated
module; "required" becomes `required` (in order); `callbacks` receives a literal in the code with the
values from the dump `base_classes[<base>]["registration"]["callbacks"]` (`optional`, `classmethod`)
**[O]** (`{}` for `NodeTreeInterfaceSocket`, absent from the dump). Rows without an indicated module belong to
`types.stubs`. The non-optional callbacks of the dump are all in the "required" column.

| Base (module) | `kind` | Required (order) | RNA name | Extra validation |
|---|---|---|---|---|
| `PropertyGroup` (`registry`) | `GENERIC` | — | `cls.__name__` **[I]** | — |
| `Operator` (`types.operator`) | `OPERATOR` | `bl_label` **[O]** | `operator_rna_name(idname)` **[O]** | `validate_operator_idname`; `bl_options` ⊆ `OPERATOR_OPTIONS` |
| `Macro` (`types.stubs`) | `OPERATOR` | `bl_label` **[I]** | same | same |
| `Panel` (`types.ui`) | `UI` | `bl_label`, `bl_space_type`, `bl_region_type`, `draw` **[O]** | `bl_idname` or `cls.__name__` **[O]** | `bl_space_type` ∈ `SPACE_TYPES`, `bl_region_type` ∈ `REGION_TYPES`, `bl_options` ⊆ `PANEL_OPTIONS`, `bl_parent_id`, `_PT_` convention |
| `Menu` (`types.ui`) | `UI` | `bl_label`, `draw` **[O]** | same **[O]** | `bl_options` ⊆ `MENU_OPTIONS`; `_MT_` convention |
| `Header` (`types.ui`) | `UI` | `bl_space_type`, `draw` **[O]** | same **[O]** | `bl_space_type` ∈ `SPACE_TYPES`; `bl_region_type` (if defined) ∈ `REGION_TYPES`; `_HT_` convention |
| `UIList` (`types.ui`) | `UI` | — **[O]** | same **[O]** | `_UL_` convention |
| `AddonPreferences` (`types.prefs`) | `GENERIC` | — **[O]** | `cls.__name__` **[I]** | — |
| `KeyingSetInfo` (`types.stubs`) | `GENERIC` | `poll`, `iterator`, `generate` **[O dump]** | `bl_idname` or `cls.__name__` **[I]** | — |
| `RenderEngine` | `GENERIC` | — | same | — |
| `Gizmo` | `GENERIC` | `draw` **[O dump]** | same | — |
| `GizmoGroup` | `GENERIC` | `setup` **[O dump]** | same | — |
| `WorkSpaceTool`, `AssetShelf`, `FileHandler`, `NodeTree` | `GENERIC` | — | same | — |
| `Node` | `GENERIC` | `poll` **[O dump]** | same | — |
| `NodeSocket` | `GENERIC` | `draw` **[O dump]** | same | — |
| `NodeTreeInterfaceSocket` | `GENERIC` | — (no entry in the dump) **[I]** | same | — |

`register_class(cls)` runs the sequence of §2.1.6 with these details:

1. `cls` is not a `type` or `registrable_base_of(cls)` is `None` → `RegistrationRuntimeError` with
   `"missing bl_rna attribute"` and `"(may not be registered)"` **[O]** (Blender cites `'type'
   instance`; Quartz cites `type(cls).__name__`).
2. `"bl_rna" in cls.__dict__` (including the base itself or another built-in type) →
   `RegistrationError(f"register_class(...): already registered as a subclass '{cls.__name__}'")`
   **[O]**.
3. Validation, in this order **[I]** (nothing is changed until it passes): (a) each name in `required`
   missing (`not hasattr(cls, name)`) → `MissingClassAttributeError(f'expected {base.__name__},
   {cls.__name__} class to have an "{name}" attribute')` **[O]**, the first in the order of the table;
   (b) class enums (only those in the "extra validation" column, and only if the attribute exists): value outside
   the list → `ClassValidationError(f'validating class: enum "{v}" not found in ({list})')` with
   `list = ", ".join(repr(i) for i in items)` **[O]**; simple enum value that is not `str` →
   `ClassValidationError` with `"expected a string"` **[I]**; `bl_options` that is not
   `set`/`frozenset` → `ClassValidationError` with `"expected a set"` **[I]**; elements of
   `bl_options` checked in `sorted(..., key=str)` (the first invalid in that order goes into the
   message); (c) `kind == "OPERATOR"`: `idname = getattr(cls, "bl_idname", cls.__name__)`; non-`str`
   → `ClassValidationError` with `"expected a string"` **[I]**; otherwise
   `validate_operator_idname(idname, cls.__name__)` **[O]**; (d) Panel with non-empty `bl_parent_id`:
   `lookup(p)` (with resolver) must return a registered subclass of `Panel`, otherwise
   `RegistrationRuntimeError(f"Registering panel class: parent '{p}' for '{name}' not found")`
   **[O]**, `name = rna_name_of(cls)`; (e) the base's `validate`, if any; (f)
   `kind == "UI"` and the RNA name does not contain `f"_{K}_"` with non-empty prefix and suffix (`K` = `PT`,
   `MT`, `HT`, `UL`) → only prints to `sys.stderr` a line with `f"'{name}' does not contain
   '_{K}_' with prefix and suffix"` **[O]**.
4. RNA name from the table. Another registered class with the same RNA name → it is unregistered before
   continuing, without error **[O]** (probes `register_new_class_same_idname`/`unregister_first`), by a
   complete `unregister_class(old)`, including its `unregister()` **[I]**. If a later step fails, the old
   one remains unregistered **[I]**.
5. `quartz.rna.install_properties(cls)`; error propagates (the `RegistrationError` of §1.6.4) and nothing is
   registered.
6. The base's `prepare(cls, rna_name)` (operators: property class, §2.5.2); error →
   `uninstall_properties(cls)` and propagates.
7. `type.__setattr__(cls, "bl_rna", RNAStruct(cls, rna_name))`; indexes by RNA name, by class and,
   for `OPERATOR`, by `operator_idname_py(rna_name)`; records the order and the owner `current_owner()`.
8. Classmethod `cls.register()` if `cls` (through the MRO, above the base) defines it **[O]** (judge
   `register.classmethod_hooks == ["register", "unregister"]`); exception propagates, the class remains
   registered **[I]**.
9. Notifies each subscriber with `("register", cls)`; subscriber exception → traceback on `stderr`,
   continues.

The registry is reentrant: `register_class` called during validation (resolver creating a
placeholder for `bl_parent_id`) works.

`unregister_class(cls)`: `not is_registered(cls)` (never registered, already unregistered, plain class
or built-in type) → `RegistrationRuntimeError(f"unregister_class(...):, missing bl_rna attribute
from '{type(cls).__name__}' instance (may not be registered)")` **[O]**. Otherwise: classmethod
`cls.unregister()` if defined **[O]**; `uninstall_properties(cls)`; removes `bl_rna` from the
`__dict__`, indexes and owner; the base's `cleanup(cls)` (operators: discards the property class;
UI: discards the attached functions, §2.5.3); notifies `("unregister", cls)`. Exception from
`cls.unregister()` propagates **after** the cleanup **[I]**.

`validate_operator_idname(idname, class_name)` **[O]** — `s = idname[:63]` (the field has
`length_max` 64; the observed message shows the idname truncated to 63 characters), rules in this
order, each failure → `RegistrationRuntimeError(f"Registering operator class '{class_name}', invalid
bl_idname '{s}', {reason}")`:

1. the first index `i` whose character is not `a-z`, `0-9`, `_` or `.` →
   `f"Invalid character at position {i}"` (`"Quartz.Probe"`, `"QUARTZ_OT_probe"` and the class name
   `"QUARTZPROBE_OT_noidname"` fall here, position 0);
2. `s.count(".") != 1` → `"Must contain 1 '.' character"` (`"quartzprobe"`, `"quartz.probe.x"`);
3. `len(s) > 60` → `"Identifier too long, maximum length is 60"` **[I for the exact threshold]**;
4. a leading digit is accepted (`"1quartz.probe"`).

`operator_rna_name("mod.op")` = `mod.upper() + "_OT_" + op` (splits at the first `"."`); without `"."` →
`ValueError`.
`operator_idname_py("MOD_OT_op")` = part before the first `"_OT_"` in lowercase + `"."` + the rest.
`operator_class(idname)`: `"_OT_"` in `idname` → converts with `operator_idname_py`; returns the
registered class or `None` (no resolver).

`lookup(rna_name, *, resolve=True)`: registered class with that RNA name; otherwise, with `resolve` and
a resolver installed, `resolver(rna_name)`; otherwise `None`. Unregistered built-in types do not
enter (the `quartz.types` catalog covers them).

**Owners and dynamic props.** `install_hooks()` installs `_on_defined(cls, identifier)`, which records
`(cls, identifier, get_property(cls, identifier).deferred, current_owner())`, and `_on_removed(cls,
identifier)`, which erases the record. `type_props_owned_by(owner)` returns, in definition order, the
pairs recorded with that owner whose `PropertyDef` is still in `cls.__dict__` (checked on the spot,
because `uninstall_properties` removes dynamic ones without going through the hook). Without `install_hooks()`, nothing
is recorded.

**`snapshot()`/`restore(snap)`**: `snapshot` stores (copies) the ordered list `(cls, rna_name,
owner)` of the registered classes, the records of dynamic props present, and
`quartz.types.ui.extensions_snapshot()`. `restore`, in this order: (1) unregisters, in reverse order
of registration, the registered classes that are not in the snapshot, without calling user `unregister()`;
(2) re-registers, in snapshot order, those that were and no longer are (same RNA name,
same owner; no user `register()`; `install_properties` and `prepare` run; the validation of
step 3 is not redone); (3) over a copy of the current records, removes the recorded dynamic props
still present that are not in the snapshot (`remove_property`) and redefines the snapshot's
absent ones (`define_property(cls, identifier, deferred)` if `"bl_rna" in cls.__dict__`); (4) replaces the
records with those of the snapshot (discards those made by the hooks during step 3, which would carry the
current owner); (5) the registration order and the owner of each class become exactly those of the
snapshot (including those that stayed registered all along); (6)
`extensions_restore(...)` (skipped if `quartz.types.ui` cannot be imported). Subscribers are
notified of steps 1–2. `restore` is idempotent and does not touch the resolver, the subscribers or
the bases. Dynamic props defined without `install_hooks()` are not seen by `snapshot/restore`.

Errors (verified by test): `RegistrationRuntimeError` (`"missing bl_rna attribute"`, `"(may not
be registered)"`, `"invalid bl_idname"`, `"Must contain 1 '.' character"`, `"Invalid character at
position 0"`, `"Identifier too long, maximum length is 60"`, `"parent '"`, `"not found"`);
`RegistrationError` (`"already registered as a subclass"`, `"could not register"`);
`MissingClassAttributeError` (`'class to have an "bl_label" attribute'` and analogues);
`ClassValidationError` (`'validating class: enum "NOPE" not found in ('`, `"expected a set"`,
`"expected a string"`); `ValueError`
(`operator_idname_py`, `operator_rna_name`); `TypeError` (`register_base` with a non-struct).

#### 2.5.2 `quartz/types/operator.py`

```python
OPERATOR_RETURN_FLAGS: tuple[str, ...] = ("RUNNING_MODAL", "CANCELLED", "FINISHED", "PASS_THROUGH", "INTERFACE")   # [O]
OPERATOR_OPTIONS: tuple[str, ...]   # items of base_classes.Operator.properties.bl_options, dump order (12) [O]
REPORT_TYPES: tuple[str, ...]       # items of Operator.functions.report.params[type], dump order (9) [O]
EVENT_TYPES: tuple[str, ...]        # items of sub_structs.Event.properties.type (196), dump order [O]
EVENT_VALUES: tuple[str, ...]       # ("ANY", "PRESS", "RELEASE", "CLICK", "DOUBLE_CLICK", "CLICK_DRAG", "NOTHING") [O]
@builtin_struct
class Operator(Struct):
    _q_registrable = True
    name: str            # rna, ro (virt): getattr(type(self), "bl_label", "")
    has_reports: bool    # rna, ro (virt): bool(self._q_reports)
    properties: "OperatorProperties"      # python member, ro: instance of the properties class that SHARES _p/_p_set
    layout: "UILayout | None"             # python member, ro: self._q_layout (None outside draw)
    options: "OperatorOptions"            # python member, ro: created on first read, all False
    macros: PropCollection                # python member, ro: empty collection
    def __new__(cls, *args, **kwargs) -> "Operator"   # super().__new__ + _q_reports = [], _q_layout = None, _q_props_inst = None
    @classmethod
    def poll_message_set(cls, message: str | Callable[..., str], *args: object) -> None
    def report(self, type: set[str], message: str) -> None
    def is_repeat(self) -> bool                                    # False
    def as_keywords(self, *, ignore: Iterable[str] = ()) -> dict[str, object]
    # ---- protocol consumed by quartz.ops / UILayout / KeyMapItem ----
    @classmethod
    def q_properties_class(cls) -> type["OperatorProperties"]
    @classmethod
    def q_new_properties(cls) -> "OperatorProperties"
    def _q_assign(self, kwargs: Mapping[str, object]) -> None
    _q_reports: list[tuple[frozenset[str], str]]
    @classmethod
    def _q_take_poll_message(cls) -> str | None
@builtin_struct
class OperatorProperties(Struct): ...     # no own props (the dump lists none); base of the per-operator classes
@builtin_struct
class OperatorOptions(Struct): ...        # is_invoke, is_repeat, is_repeat_last, use_cursor_region, is_grab_cursor: BOOL ro, default False [I]
@builtin_struct
class OperatorFileListElement(PropertyGroup): ...   # only the inherited prop "name"; type of CollectionProperty(type=OperatorFileListElement)
@builtin_struct
class Event(Struct):                      # all the scalar/array props of the dump (ascii, unicode, value, value_prev, type, type_prev,
                                          # direction, is_repeat, is_consecutive, mouse_*, pressure, tilt, is_tablet, is_mouse_absolute,
                                          # shift, ctrl, alt, oskey, hyper) with meta={"readonly": True}; ndof_motion and xr: python members -> None
    @classmethod
    def q_synthetic(cls, type: str = "NONE", value: str = "NOTHING", **fields: object) -> "Event"
```

Rules:

1. **Properties class** (`prepare` of the `Operator` base, step 6 of §2.1.6): with
   `ids = cls.__dict__["_q_installed"]` (the props from the class annotations, from the user parent
   classes and from the mixins, in installation order), create
   `P = type(OperatorProperties)(rna_name, (OperatorProperties,), {"__module__": cls.__module__,
   "__qualname__": rna_name, "_q_strict_attrs": True, "__annotations__": {i: get_property(cls,
   i).deferred for i in ids}})` and apply `builtin_struct(P, identifier=rna_name)` — the
   `install_properties` of `builtin_struct` builds in `P` (owner `P`) an equivalent `PropertyDef`
   for each `_PropertyDeferred`, in the same order, and writes `P.__dict__["_q_installed"]`
   (`clone_for` is not used: `builtin_struct` would overwrite `_q_installed`). Hence `P.__name__ ==
   P.bl_rna.identifier == "MOD_OT_name"` and the coercion messages cite `"MOD_OT_name.prop"`
   **[O]**. `P` is stored in the operator class's own `__dict__` (`_q_props_class`; outside
   the registry indexes and the `quartz.types` catalog); `cleanup` removes it. `q_properties_class()`
   reads only `cls.__dict__` (an unregistered subclass of a registered operator does not inherit `P`);
   absent → `RegistrationRuntimeError(f"{cls.__name__} is not registered")`. Since `P` and the operator
   have the same RNA identifier, `OperatorProperties.bl_rna_get_subclass_py(name)` returns `P` and
   `Operator.bl_rna_get_subclass_py(name)` returns the operator.
2. `q_new_properties()`: a new instance of `P` with its own `_p` (defaults only).
   `op.properties`: an instance of `P` created on first read and stored in `_q_props_inst`, whose `_p`
   and `_p_set` are **the same objects** as those of `op` — `op.count` and `op.properties.count` read and write
   the same value; `op.properties.is_property_set("x")` is true only if `x` was passed **[O]**.
3. `_q_assign(kwargs)`, in item order: identifier without a `PropertyDef` in `P` →
   `PropertyTypeError(f'Converting py args to operator properties:: keyword "{k}" unrecognized')`
   **[O]**; otherwise `setattr(self.properties, k, v)`; `PropertyTypeError`/`PropertyValueError`/
   `ReadOnlyError` raised there are re-raised with the same class, `__cause__` = original and the
   message with the prefix `"bpy_struct: item.attr = val: "` replaced by `"Converting py args to
   operator properties: "` **[O]** (e.g.: `"Converting py args to operator properties:
   QUARTZ_PROBE_OT_hello.count expected an int type, not str"`, `'... enum "Z" not found in ('A',
   'B')'`). Out-of-range values are clamped by the L1 coercion **[O]**.
4. `report(type, message)`: `type` must be a non-empty `set`/`frozenset` of items from
   `REPORT_TYPES`; otherwise `PropertyTypeError` with `f'enum "{v}" not found in ('` (or `"expected a
   set"`) **[I]**; a non-`str` `message` → `PropertyTypeError`. Appends `(frozenset(type), message)` to
   `_q_reports`. Nothing is printed here (printing is done by `quartz.ops`, §2.6.3).
5. `poll_message_set(message, *args)` stores `(message, args)` in a module-level dictionary keyed
   by the class `cls` that received it (the one from `poll`; no inheritance between classes); a new call replaces it.
   `_q_take_poll_message()` returns `str(message(*args))` if `message` is callable, otherwise
   `message`, and erases the entry for `cls`; no entry → `None` **[I]**. Whoever calls `poll` consumes
   the message right afterwards, whether or not it succeeds (§2.6.3), so that it does not leak into the next
   call.
6. `as_keywords(ignore=())` → `{k: getattr(self, k)}` for each `PropertyDef` of `P`, in
   declaration order, except `ignore` **[O]** (only the declared ones; ordinary instance attributes are not included).
7. `Event.q_synthetic(type, value, **fields)`: a new instance; each field (including `type` and
   `value`), in the order `type`, `value` and then that of `fields`, is written with
   `pdef.write_raw(ev, pdef.coerce(v, ev))` (without `_p_set`, callbacks or hooks); a field that is not a
   declared prop of `Event` (including `ndof_motion`/`xr`) → `PropertyTypeError(f"Event has no
   field '{k}'")`; invalid enum → the L1 enum message (`'enum "'`). A normal write to `Event` →
   `ReadOnlyError` (all are read-only **[O]**).

Errors: `PropertyTypeError` (`'Converting py args to operator properties:: keyword "'`,
`"Converting py args to operator properties: "`, `'enum "'`); `PropertyValueError` (same prefix,
array size); `RegistrationRuntimeError` (`"is not registered"`); `ReadOnlyError`
(`'from "Event" is read-only'`).

#### 2.5.3 `quartz/types/ui.py`

```python
SPACE_TYPES: tuple[str, ...]     # items of base_classes.Panel.properties.bl_space_type, dump order (19) [O]
REGION_TYPES: tuple[str, ...]    # items of base_classes.Panel.properties.bl_region_type, dump order (17) [O]
PANEL_OPTIONS: tuple[str, ...] = ("DEFAULT_CLOSED", "HIDE_HEADER", "INSTANCED", "HEADER_LAYOUT_EXPAND")   # [O]
MENU_OPTIONS: tuple[str, ...] = ("SEARCH_ON_KEY_PRESS",)                                                  # [O]
class _GenericUI:                # mixin (not a Struct); only classmethods
    @classmethod
    def append(cls, draw_func: Callable[[object, object], None]) -> None
    @classmethod
    def prepend(cls, draw_func: Callable[[object, object], None]) -> None
    @classmethod
    def remove(cls, draw_func: Callable) -> None
    @classmethod
    def is_extended(cls) -> bool
@builtin_struct
class Panel(Struct, _GenericUI):
    _q_registrable = True
    text: str            # rna (STRING, default "")
    use_pin: bool        # rna (default False)
    is_popover: bool     # rna, ro (default False)
    layout: "UILayout | None"     # python member, ro: self._q_layout
    custom_data: None             # python member, ro: None
@builtin_struct
class Menu(Struct, _GenericUI):
    _q_registrable = True
    layout: "UILayout | None"     # python member, ro
    def draw_preset(self, context: object) -> None
    @classmethod
    def draw_collapsible(cls, context: object, layout: "UILayout") -> None
    def path_menu(self, searchpaths: Sequence[str], operator: str, *, props_default: Mapping[str, object] | None = None,
                  prop_filepath: str = "filepath", filter_ext: Callable[[str], bool] | None = None,
                  filter_path: Callable[[str], bool] | None = None, display_name: Callable[[str], str] | None = None,
                  add_operator: str | None = None, add_operator_props: Mapping[str, object] | None = None,
                  translate: bool = True) -> None
@builtin_struct
class Header(Struct, _GenericUI):
    _q_registrable = True
    layout: "UILayout | None"     # python member, ro
@builtin_struct
class UIList(Struct, _GenericUI):
    _q_registrable = True
    list_id: str                  # rna, ro (maxlen 256)
    layout_type: str              # rna, ro: enum ("DEFAULT", "COMPACT"), default "DEFAULT"
    use_filter_show: bool; filter_name: str; use_filter_invert: bool        # rna (filter_name maxlen 256)
    use_filter_sort_alpha: bool; use_filter_sort_reverse: bool; use_filter_sort_lock: bool
    bitflag_filter_item: int      # rna, ro (INT UNSIGNED, dump default 0); virt -> 1 << 30 [I]
    bitflag_item_never_show: int  # rna, ro (default 0); virt -> 1 << 29 [I]
    layout: "UILayout | None"     # python member, ro
@builtin_struct
class UI_UL_list(UIList):
    @staticmethod
    def filter_items_by_name(pattern: str, bitflag: int, items: Iterable, propname: str = "name",
                             flags: list[int] | None = None, reverse: bool = False) -> list[int]
    @staticmethod
    def sort_items_helper(sort_data: list[tuple], key: Callable, reverse: bool = False) -> list[int]
    @staticmethod
    def sort_items_by_name(items: Iterable, propname: str = "name") -> list[int]
def draw_funcs_owned_by(owner: str) -> list[tuple[type, Callable]]
def iter_extended() -> Iterator[tuple[type, tuple[Callable, ...]]]
def extensions_snapshot() -> object
def extensions_restore(snap: object) -> None
def draw_sequence(cls: type) -> tuple[Callable, ...]   # functions to call when drawing, in order (used by quartz.ui)
```

Rules:

1. Extensions live in a module-level table (not in the class `__dict__`), per **exact** class (not
   inherited by subclasses **[I]**). Each entry: `(function, owner = registry.current_owner())`.
   `append` adds at the end; `prepend` inserts at the start; duplicates are accepted **[I]**;
   `remove` removes the first occurrence (compared by `==`, so that equal bound methods
   match) and is silent if the function is not there **[O]**.
2. `is_extended()` is `False` until the first `append`/`prepend` and becomes `True` **[O]**; it remains
   `True` after everything is removed (the class has already been "wrapped") **[I]**.
   `extensions_restore`/the registry `cleanup` set it back to `False`.
3. `draw_sequence(cls)` = the `prepend` functions (most recent first), then `cls.draw` if the
   class defines it (`hasattr(cls, "draw")`, common rule 3), then the `append` ones in order **[O]**
   (Blender shows 2 functions after an `append` on a menu with `draw`).
4. `draw_funcs_owned_by(owner)` lists `(class, function)` still attached with that owner, ordered
   by class (order of each class's first extension) and, within the class, by position in
   `draw_sequence`. `iter_extended()` lists, in order of first extension, the classes with
   `is_extended()` true and their attached functions in `draw_sequence` order (without `draw`).
5. `extensions_snapshot()` copies the table (lists and flags); `extensions_restore(snap)` replaces it
   with the copy. The registry `cleanup` for `UI` bases erases the entry of the unregistered class
   **[I]**.
6. `Menu.draw_collapsible(context, layout)` records `layout.menu(<RNA name of cls>)` **[I]**.
   `Menu.draw_preset(context)`: if the class has `preset_subdir` and `preset_operator`, calls
   `self.path_menu(quartz.utils.preset_paths(self.preset_subdir), self.preset_operator,
   props_default=getattr(self, "preset_operator_defaults", None), add_operator=getattr(self,
   "preset_add_operator", None))`; otherwise nothing **[L]**. `path_menu`: for each existing directory
   in `searchpaths`, files (not folders) sorted by `str.casefold` of the name (stable; the
   `sort_key` of `quartz.types.naming` is not imported, §0.6), filtered by extension (`filter_ext`
   receives the extension with a dot; default: all) and `filter_path`; for each one it records
   `props = self.layout.operator(operator, text=name)` (name = `display_name(path)` or
   `quartz.path.display_name(file)`), and assigns `props_default` and `prop_filepath = path`
   when `props` accepts them; `add_operator` records an extra `operator` at the end **[I]**.
7. `UI_UL_list.filter_items_by_name` **[L]**: empty `pattern` or empty `items` → returns `flags`
   (the same list) or `[]` if `flags` is `None`; otherwise absent `flags` → `[0] * len(items)`; an item
   whose `name = getattr(item, propname, None)` is non-empty and matches
   `fnmatch.fnmatchcase(name.casefold(), f"*{pattern.casefold()}*")` gets `flags[i] |= bitflag`
   (with `reverse`, those that do **not** match); returns `flags`. `sort_items_helper(sort_data, key,
   reverse)`: `sort_data` is a list of `(original_index, ...)`; sorts it in place by `key`
   (stable, `reverse`) and returns `neworder` with `neworder[orig] = new_position` **[L]**.
   `sort_items_by_name(items, propname)`: `sort_items_helper` with `(i, getattr(item, propname, ""))`
   and a `casefold` key **[I]**.
8. `layout` of `Panel`/`Menu`/`Header`/`UIList` is written by `quartz.ui` into `_q_layout` and read as
   `getattr(self, "_q_layout", None)` (an instance created outside `quartz.ui` reads `None`).
9. A missing `Header.bl_region_type` is `"HEADER"` for whoever needs it (dump default), read
   with `getattr(cls, "bl_region_type", "HEADER")` (common rule 3).

Errors: none besides those of the registry (validation of the table in §2.5.1).

#### 2.5.4 `quartz/types/prefs.py`

```python
@builtin_struct
class Preferences(Struct):
    active_section: str            # rna ENUM (17 items in the dump), default "INTERFACE" [O]
    app_template: str              # rna (maxlen 64)
    use_preferences_save: bool     # rna, default False (dump: True — headless divergence; never saves)
    is_dirty: bool                 # rna, default False
    version: tuple[int, int, int]  # rna ro (INT XYZ [3], dump default (0, 0, 0)); virt -> quartz.app.version [I]
    # the eight below: rna PointerProperty(type=<sub-struct>) — pointer to non-ID struct, thus read-only and with
    # stored lazy instance (same identity always, §1.6.4); the sub-struct classes come earlier in the module
    view: "PreferencesView"; edit: "PreferencesEdit"; system: "PreferencesSystem"; inputs: "PreferencesInput"
    filepaths: "PreferencesFilePaths"; extensions: "PreferencesExtensions"; experimental: "PreferencesExperimental"
    keymap: "PreferencesKeymap"
    addons: "Addons"               # python member, ro; same instance always
    themes: PropCollection; ui_styles: PropCollection; autoexec_paths: PropCollection   # python members, ro, empty collections (common rule 6)
    def q_reset(self) -> None
class Addons(PropCollection):      # Addon items; _q_key(item) = item.module
    def new(self) -> "Addon"
    def remove(self, addon: "Addon") -> None
@builtin_struct
class Addon(Struct):
    module: str                    # rna (maxlen 128), rw
    preferences: "AddonPreferences | None"    # python member, ro
@builtin_struct
class AddonPreferences(Struct):
    _q_registrable = True
    layout: "UILayout | None"      # python member, ro; optional user draw
@builtin_struct
class PreferencesEdit(Struct):        # use_global_undo: bool = True [O]; undo_steps: int (virt <-> settings.undo_steps; INT 0..256) [I];
                                      # undo_memory_limit: int = 0 [I]
@builtin_struct
class PreferencesView(Struct):        # ui_scale: float = 1.0; show_developer_ui: bool = False; show_tooltips: bool = True;
                                      # language: dynamic enum ("DEFAULT" + translations.locales), virt <-> translations.locale [I]
@builtin_struct
class PreferencesFilePaths(Struct):   # temporary_directory: str (ro, virt: str(quartz.app.paths.temp_dir()));
                                      # script_directories, asset_libraries: python members, ro, empty collections
@builtin_struct
class PreferencesExtensions(Struct):  # repos: python member, ro: collection of UserExtensionRepo, one per quartz.app.paths.extension_repos()
@builtin_struct
class UserExtensionRepo(Struct):      # name, module, directory: str; enabled: bool; source: enum ("USER", "SYSTEM"); use_remote_url: bool — all ro (virt)
@builtin_struct
class PreferencesSystem(Struct): ...
@builtin_struct
class PreferencesInput(Struct): ...
@builtin_struct
class PreferencesExperimental(Struct): ...
@builtin_struct
class PreferencesKeymap(Struct): ...
```

Rules:

1. `Preferences()` works without a session (the session creates one, §2.6.1). An unknown attribute on
   any type in this module (except `AddonPreferences` and subclasses) → `AttributeError`.
2. `Addons.new()` appends an `Addon` with `module = ""` and returns it; `remove(addon)` removes the
   instance; absent → `LinkError` with `"not found"` **[I]**. Key = `Addon.module`
   (`prefs.addons["mod"]`, `"mod" in prefs.addons`, `get`). Insertion order.
3. `Addon.preferences` **[O]** (resolution by `bl_idname == module`): iterates
   `registry.iter_classes(AddonPreferences)` and picks the **last** registered one **[I]** with
   `getattr(c, "bl_idname", None) == self.module`; none → `None`. The
   instance is created on first read with `c._q_new_child(owner=self, path="preferences")` and
   stored; if the chosen class changes (re-registration), another is created. The `addon_lifecycle` probe shows
   the type `QuartzProbePrefs` with `bl_idname == __package__`.
4. `PreferencesEdit.undo_steps` reads and writes `quartz.app.settings.settings.undo_steps`;
   `PreferencesView.language` reads `translations.locale` and writes with `translations.set_locale`; the
   items are `("DEFAULT",) + translations.locales` (read on the spot); writing `"DEFAULT"` calls
   `set_locale("en_US")` **[I]**.
5. `PreferencesExtensions.repos`: on each read, one item per `(module, dir)` from
   `quartz.app.paths.extension_repos()` (same instance per `module` across reads): `name =
   module` **[I]**, `directory = str(dir)`, `enabled = True`, `source = "SYSTEM"` if `module ==
   "system"`, otherwise `"USER"`, `use_remote_url = False` **[O]** (`addon_lifecycle` probe; the remote repo
   `blender_org` does not exist in Quartz).
6. `q_reset()`: `property_unset` of each declared prop of `Preferences` and of each sub-struct already
   created; empties `addons` (discarded `AddonPreferences` instances). Does NOT touch
   `quartz.app.settings` or `translations` (they have their own snapshot).

Errors: `LinkError` (`"not found"`); `AttributeError` (unknown attribute); `ReadOnlyError`
(`version`, `temporary_directory`).

#### 2.5.5 `quartz/types/stubs.py`

Inert registrable bases (referred to by §0.3): they register, validate the required items of the table in
§2.5.1 and are never executed by Quartz.

```python
@builtin_struct
class Macro(Struct):
    _q_registrable = True
    @classmethod
    def define(cls, opname: str) -> object        # records opname; returns object with .properties (the operator's q_new_properties() if registered,
                                                   # otherwise an object that accepts any attribute) [I]
    @classmethod
    def q_properties_class(cls) -> type["OperatorProperties"]   # same rule as Operator (shared prepare)
    @classmethod
    def q_new_properties(cls) -> "OperatorProperties"
    def _q_assign(self, kwargs: Mapping[str, object]) -> NoReturn   # NotImplementedInQuartz("Macro operators")
@builtin_struct
class RenderEngine(Struct): _q_registrable = True
@builtin_struct
class HydraRenderEngine(RenderEngine): ...       # not a registered base: subclasses resolve to RenderEngine
@builtin_struct
class KeyingSetInfo(Struct): _q_registrable = True
@builtin_struct
class Gizmo(Struct): _q_registrable = True
@builtin_struct
class GizmoGroup(Struct): _q_registrable = True
@builtin_struct
class WorkSpaceTool(Struct): _q_registrable = True
@builtin_struct
class AssetShelf(Struct): _q_registrable = True
@builtin_struct
class FileHandler(Struct): _q_registrable = True
@builtin_struct
class Node(Struct): _q_registrable = True
@builtin_struct
class NodeSocket(Struct): _q_registrable = True
@builtin_struct
class NodeTree(Struct): _q_registrable = True       # NOT an ID (bpy.data.node_groups is a ghost)
@builtin_struct
class NodeTreeInterfaceSocket(Struct): _q_registrable = True
@builtin_struct
class Space(Struct):                                 # inert, not registrable
    @classmethod
    def draw_handler_add(cls, callback: Callable, args: tuple, region_type: str, draw_type: str) -> object   # returns an opaque handle
    @classmethod
    def draw_handler_remove(cls, handle: object, region_type: str) -> None
# @builtin_struct subclasses of Space, one per name: SpaceView3D, SpaceImageEditor, SpaceNodeEditor, SpaceTextEditor, SpaceProperties,
# SpaceOutliner, SpaceFileBrowser, SpaceSequenceEditor, SpaceClipEditor, SpaceGraphEditor, SpaceDopeSheetEditor, SpaceNLA, SpaceConsole,
# SpaceInfo, SpacePreferences, SpaceSpreadsheet
def draw_handlers(space_cls: type | None = None) -> list[tuple[type, Callable, tuple, str, str]]   # (class, callback, args, region, draw_type)
```

Rules:

1. The bases do not declare props (§2.4 does not check them) nor define callbacks. The dump callbacks
   of each base go to `register_base(..., callbacks=...)` and the non-optional ones to
   `required` (table in §2.5.1): e.g. `KeyingSetInfo` without `generate` →
   `MissingClassAttributeError(f'expected KeyingSetInfo, {name} class to have an "generate"
   attribute')`.
2. `Macro` uses `kind="OPERATOR"`, the same `bl_idname` validation, the same RNA name
   (`"MOD_OT_name"`) and the same `prepare`/`cleanup` as `Operator`: it appears in
   `registry.operator_class`/`iter_operators`, and `quartz.ops` finds it and raises
   `NotImplementedInQuartz("Macro operators")` before `poll` (§2.6.3); as a safeguard,
   `Macro._q_assign` raises the same error **always** (also with empty `kwargs`; text `"Macro
   operators is not implemented in Quartz"`).
3. `HydraRenderEngine` has its own `bl_rna` (it appears in the `quartz.types` catalog), but
   `registrable_base_of(Sub)` for a user subclass returns `RenderEngine`.
4. `Space.draw_handler_add` stores `(cls, callback, args, region_type, draw_type)` in a module-level
   list and returns an opaque handle (a new object, compared by identity); nothing is ever called
   (in background Blender does not draw) **[I]**.
   `draw_handler_remove(handle, region_type)` removes the handle; unknown handle → silent
   **[I]**. `draw_handlers(space_cls)` lists the entries (all of them, or only those of that exact class).
5. `utils.register_tool` (§2.5.7) accepts subclasses of `WorkSpaceTool` without registering them.

Errors: `MissingClassAttributeError` (required items from the dump); `NotImplementedInQuartz` (`"Macro
operators"`).

#### 2.5.6 `quartz/ui.py`

```python
UILAYOUT_FUNCTIONS: Mapping[str, tuple[str, ...]]   # exact copy (116 keys, same order and lists) of extras.UILayout_functions from the dump [O]
UILAYOUT_OUTPUTS: Mapping[str, tuple[str, ...]]     # names in UILAYOUT_FUNCTIONS that are RETURN values, not parameters (table below);
                                                    # only the functions in the table are keys (for the others: UILAYOUT_OUTPUTS.get(name, ()))
OPERATOR_CONTEXTS: tuple[str, ...] = ("INVOKE_DEFAULT", "INVOKE_REGION_WIN", "INVOKE_REGION_CHANNELS", "INVOKE_REGION_PREVIEW",
                                      "INVOKE_AREA", "INVOKE_SCREEN", "EXEC_DEFAULT", "EXEC_REGION_WIN", "EXEC_REGION_CHANNELS",
                                      "EXEC_REGION_PREVIEW", "EXEC_AREA", "EXEC_SCREEN")   # same values and order as quartz.ops.EXEC_CONTEXTS (without importing it) [O]
@dataclass(frozen=True)
class LayoutIssue:
    kind: str        # "UNKNOWN_PROPERTY" | "UNKNOWN_OPERATOR" | "UNKNOWN_MENU" | "UNKNOWN_PANEL" | "UNKNOWN_FUNCTION" | "DRAW_EXCEPTION" | "POLL_EXCEPTION"
    message: str; detail: Mapping[str, object]
@dataclass
class LayoutNode:
    kind: str; args: tuple; kwargs: dict[str, object]; children: list["LayoutNode"]
@builtin_struct
class UILayout(Struct):
    # rna props [I]: active=True, enabled=True, alert=False, alignment="EXPAND" (EXPAND LEFT CENTER RIGHT), scale_x=1.0, scale_y=1.0,
    # ui_units_x=0.0, ui_units_y=0.0, use_property_split=False, use_property_decorate=True,
    # operator_context="INVOKE_REGION_WIN" (OPERATOR_CONTEXTS), emboss="NORMAL" (NORMAL NONE PULLDOWN_MENU PIE_MENU NONE_OR_STATUS),
    # activate_init=False, active_default=False
    def __init__(self) -> None                     # UILayout() = new root ("ROOT" node, its own issues list)
    def row(self, align: bool = False, heading: str = "", heading_ctxt: str = "", translate: bool = True) -> "UILayout"
    def column(self, align: bool = False, heading: str = "", heading_ctxt: str = "", translate: bool = True) -> "UILayout"
    def column_flow(self, columns: int = 0, align: bool = False) -> "UILayout"
    def grid_flow(self, row_major: bool = False, columns: int = 0, even_columns: bool = False, even_rows: bool = False,
                  align: bool = False) -> "UILayout"
    def box(self) -> "UILayout"
    def split(self, factor: float = 0.0, align: bool = False) -> "UILayout"
    def panel(self, idname: str, default_closed: bool = False) -> tuple["UILayout", "UILayout | None"]
    def panel_prop(self, data: object, property: str) -> tuple["UILayout", "UILayout | None"]
    def menu_pie(self) -> "UILayout"
    def prop(self, data: object, property: str, text: str | None = None, text_ctxt: str = "", translate: bool = True,
             icon: str = "NONE", placeholder: str = "", expand: bool = False, slider: bool = False, toggle: int = -1,
             icon_only: bool = False, event: bool = False, full_event: bool = False, emboss: bool = True, index: int = -1,
             icon_value: int = 0, invert_checkbox: bool = False, text_align: str = "") -> None
    def props_enum(self, data: object, property: str) -> None
    def prop_menu_enum(self, data: object, property: str, text: str | None = None, text_ctxt: str = "", translate: bool = True,
                       icon: str = "NONE") -> None
    def prop_enum(self, data: object, property: str, value: str, text: str | None = None, text_ctxt: str = "",
                  translate: bool = True, icon: str = "NONE") -> None
    def prop_search(self, data: object, property: str, search_data: object, search_property: str, text: str | None = None,
                    text_ctxt: str = "", translate: bool = True, icon: str = "NONE", results_are_suggestions: bool = False,
                    item_search_property: str = "") -> None
    def prop_tabs_enum(self, data: object, property: str, data_highlight: object = None, property_highlight: str = "",
                       icon_only: bool = False, expand_as: str = "") -> None
    def prop_decorator(self, data: object, property: str, index: int = -1) -> None
    def operator(self, operator: str, text: str | None = None, text_ctxt: str = "", translate: bool = True, icon: str = "NONE",
                 emboss: bool = True, depress: bool = False, icon_value: int = 0, search_weight: float = 0.0) -> "OperatorProperties"
    def operator_enum(self, operator: str, property: str, icon_only: bool = False) -> None
    def operator_menu_enum(self, operator: str, property: str, text: str | None = None, text_ctxt: str = "",
                           translate: bool = True, icon: str = "NONE") -> "OperatorProperties"
    def label(self, text: str = "", text_ctxt: str = "", translate: bool = True, icon: str = "NONE", icon_value: int = 0) -> None
    def menu(self, menu: str, text: str | None = None, text_ctxt: str = "", translate: bool = True, icon: str = "NONE",
             icon_value: int = 0) -> None
    def menu_contents(self, menu: str) -> None
    def popover(self, panel: str, text: str | None = None, text_ctxt: str = "", translate: bool = True, icon: str = "NONE",
                icon_value: int = 0, direction: str = "") -> None
    def separator(self, factor: float = 1.0, type: str = "AUTO") -> None
    def separator_spacer(self) -> None
    def progress(self, text: str = "", text_ctxt: str = "", translate: bool = True, factor: float = 0.0, type: str = "BAR") -> None
    def context_pointer_set(self, name: str, data: object) -> None
    def context_string_set(self, name: str, value: str) -> None
    def template_list(self, listtype_name: str, list_id: str, dataptr: object, propname: str, active_dataptr: object,
                      active_propname: str, item_dyntip_propname: str = "", rows: int = 5, maxrows: int = 5, type: str = "DEFAULT",
                      columns: int = 9, sort_reverse: bool = False, sort_lock: bool = False) -> None
    def template_ID(self, data: object, property: str, new: str = "", open: str = "", unlink: str = "", filter: str = "ALL",
                    live_icon: bool = False, text: str | None = None, text_ctxt: str = "", translate: bool = True) -> None
    def template_popup_confirm(self, operator: str, text: str | None = None, text_ctxt: str = "", translate: bool = True,
                               icon: str = "NONE", cancel_text: str = "", cancel_default: bool = False) -> "OperatorProperties | None"
    def icon(self, data: object) -> int
    def enum_item_name(self, data: object, property: str, identifier: str) -> str
    def enum_item_description(self, data: object, property: str, identifier: str) -> str
    def enum_item_icon(self, data: object, property: str, identifier: str) -> int
    def __getattr__(self, name: str) -> Callable[..., object]
    def q_tree(self) -> LayoutNode
    q_issues: list[LayoutIssue]                # the SAME list across the whole tree (the root's)
@dataclass
class DrawResult:
    layout: UILayout | None; poll: bool | None; issues: list[LayoutIssue]
    @property
    def ok(self) -> bool                       # no DRAW_EXCEPTION/POLL_EXCEPTION issue
def draw_ui(cls: type, context: object | None = None, *, check_poll: bool = True) -> DrawResult
def draw_panel(cls: type, context: object | None = None) -> DrawResult
def draw_menu(cls: type, context: object | None = None) -> DrawResult
def draw_ui_list(cls: type, data: object, propname: str, context: object | None = None) -> DrawResult
def placeholder_type(name: str, kind: str, *, owner: str = "quartz.placeholder") -> type
```

`UILAYOUT_OUTPUTS` **[I]**: `row`, `column`, `column_flow`, `grid_flow`, `box`, `split`,
`menu_pie` → `("layout",)`; `panel`, `panel_prop` → `("layout_header", "layout_body")`; `icon`,
`enum_item_icon` → `("icon_value",)`; `enum_item_name` → `("name",)`; `enum_item_description` →
`("description",)`; `operator`, `operator_menu_hold`, `operator_menu_enum`,
`template_popup_confirm` → `("properties",)`; `template_recent_files` → `("found",)`. For each
function with an explicit signature, the parameter names (without `self`) MUST be exactly
`UILAYOUT_FUNCTIONS[name]` minus those in `UILAYOUT_OUTPUTS[name]`, in order (defaults **[I]**).

Recorder rules:

1. Each call records a `LayoutNode(kind=<function name>, args=(), kwargs=<parameters
   actually passed, positional ones mapped to their names>, children=[])` appended to the `children`
   of this layout's node. Functions that return a layout create a child `UILayout` whose node is the recorded one;
   the child copies the parent's 14 prop values on creation **[I]**; assigning props does not record nodes.
   `panel`/`panel_prop` record a node with two children (`"layout_header"`, `"layout_body"`) and
   return `(header, body)`; `body` is `None` if `default_closed` (or, in `panel_prop`, if
   `getattr(data, property)` is falsy) **[I]**.
2. **Property validation** (`prop`, `props_enum`, `prop_menu_enum`, `prop_enum`,
   `prop_search` — `data`/`property` and `search_data`/`search_property` —, `prop_tabs_enum`,
   `prop_decorator`, `panel_prop`, `template_ID`, `template_list` — `dataptr`/`propname` and
   `active_dataptr`/`active_propname` — and the generic functions whose parameters in the dump start
   with `data`, `property`): valid if `data` is a `Struct` and (`get_property(data, property)` exists,
   or `type(data)` has a data descriptor with that name in the MRO, or `property` is `'["key"]'` with the
   key present in `data`). Otherwise it records `LayoutIssue("UNKNOWN_PROPERTY", f"{T}.{property} not
   found", {"function": name, "struct": T, "property": property})` (`T` =
   `type(data).bl_rna.identifier` if it exists, otherwise `type(data).__name__`; `data is None` →
   `"None"`) and, if `type(data)` is a built-in type (`"_q_builtin"` in its own `__dict__`) and is not an
   operator properties class (strict subclass of `OperatorProperties`, §2.5.2),
   `hooks.note_missing(f"bpy.types.{T}.{property}")`. Never raises (divergence 11 of
   ARCHITECTURE §13).
3. `operator(...)`/`operator_menu_enum(...)`/`template_popup_confirm(...)`/`operator_enum(...)`:
   `cls = registry.operator_class(operator)`; if found, `operator`, `operator_menu_enum` and
   `template_popup_confirm` return `cls.q_new_properties()` (the assignments made during drawing go to that
   instance, stored in `node.kwargs["properties"]`) and `operator_enum` returns `None`; if missing,
   `LayoutIssue("UNKNOWN_OPERATOR", f"operator {operator} not found", {"operator": operator})`,
   `hooks.note_missing(f"bpy.ops.{idname_py}")` (`idname_py = registry.operator_idname_py(operator)`
   if `"_OT_" in operator`, otherwise `operator`) and it returns an internal object that accepts and stores
   any attribute (`operator_enum`: `None`) **[I]**. `template_popup_confirm` with `operator == ""`
   (cancel button only) does not look up an operator, records no issue and returns `None` **[I]**.
4. `menu`/`menu_contents`: `registry.lookup(menu)` must be a subclass of `Menu`; otherwise
   `LayoutIssue("UNKNOWN_MENU", ..., {"menu": menu})`. `popover(panel)`: same with `Panel` →
   `"UNKNOWN_PANEL"`. The submenu/panel is not drawn.
5. `icon(data)` → `0`; `enum_item_name/description/icon`: the item of
   `get_property(data, property).items_for(data, hooks.current_context())` with that identifier
   → `name` / `description` / `icon` if `int`, otherwise `0`; missing item, missing prop or a prop that
   is not an `EnumDef` → `""`/`""`/`0` (with the issue from rule 2 if the prop does not exist) **[I]**.
6. `__getattr__(name)` (only for nonexistent attributes; names starting with `"_"` →
   `AttributeError`): `name` in `UILAYOUT_FUNCTIONS` without an explicit model → generic recorder
   (accepts `*args, **kwargs`, records `args`/`kwargs` as received; returns a child `UILayout` if
   `UILAYOUT_OUTPUTS.get(name) == ("layout",)`; if the output is `("properties",)`, treats the idname
   (`args[0]` or `kwargs["operator"]`) as in `operator` (rule 3); otherwise `None`). Any other name:
   `settings.strict_layout` → `AttributeError(f"'UILayout' object has no attribute '{name}'")`;
   otherwise it returns a recorder that, **when called**, records the node,
   `LayoutIssue("UNKNOWN_FUNCTION", ..., {"function": name})` and
   `hooks.note_missing(f"bpy.types.UILayout.{name}")`.
7. `q_tree()` returns this layout's node (the root returns the `"ROOT"` node).

Drawing rules:

1. `draw_ui(cls, context=None, *, check_poll=True)`: if `cls` is not a subclass of
   `Panel`/`Menu`/`Header`/`UIList` → `TypeError` with `"expects a Panel, Menu, Header or UIList
   subclass"`. `context` `None` → `hooks.current_context()` (may remain `None`).
2. Poll: with `check_poll` and `hasattr(cls, "poll")` → `ok = bool(cls.poll(context))`; exception →
   traceback on `sys.stderr`, `LayoutIssue("POLL_EXCEPTION", ...)` and `ok = False`; falsy `ok` →
   `DrawResult(layout=None, poll=False, issues=[...])` without drawing. If poll was not evaluated, `poll =
   None`.
3. `inst = cls()`; `root = UILayout()`; `inst._q_layout = root`. `Panel`: `draw_header` and
   `draw_header_preset` (if defined) draw into children of `root` with `kind` `"HEADER"` and
   `"HEADER_PRESET"` (with `inst._q_layout` pointing to the child during the call and returning to
   `root` afterwards), before the body; an exception in them gets the same treatment as in rule 4. `UIList`:
   only `draw_filter(context, root)` if defined **[I]**.
4. Body: each `fn` of `quartz.types.ui.draw_sequence(cls)` is called as `fn(inst, context)`;
   before each one, `root.operator_context` returns to the value it had before the 1st function **[L]**. An exception
   (`Exception`) → traceback on `sys.stderr`, `LayoutIssue("DRAW_EXCEPTION", f"{type}: {msg}",
   {"class": RNA name, "function": fn.__qualname__, "traceback": text})` and it proceeds to the next
   function; it never propagates **[L]**.
5. Returns `DrawResult(root, poll, list(root.q_issues))`.
6. `draw_panel`/`draw_menu` require a subclass of `Panel`/`Menu` (otherwise `TypeError`) and delegate
   to `draw_ui`.
7. `draw_ui_list(cls, data, propname, context=None)`: requires a subclass of `UIList`; `inst = cls()`
   with `list_id` written by `write_raw` (`""`); invalid property → `UNKNOWN_PROPERTY` (no
   exception) and returns with no items. `items = list(getattr(data, propname))`; if the class defines
   `filter_items`, `flags, neworder = inst.filter_items(context, data, propname)` (an exception, or a
   non-empty list whose size ≠ `len(items)` → `DRAW_EXCEPTION`, and `flags = neworder = []`);
   `flag_i = flags[i]` if `flags` is non-empty, otherwise `inst.bitflag_filter_item`; item `i` is
   visible if `flag_i & inst.bitflag_filter_item` and not `flag_i & inst.bitflag_item_never_show`;
   the visible ones are traversed in ascending order of `neworder[i]` (new position of item `i`;
   empty `neworder` = identity); each one gets a child `row = root.row()` and
   `inst.draw_item(context, row, data, item, 0, data, propname, i, flag_i)` if defined, otherwise
   `row.label(text=getattr(item, "name", ""))` **[I]**; an exception in `draw_item` → rule 4 and proceeds
   to the next item; then `draw_filter` in a `"FILTER"` child.
8. `placeholder_type(name, kind, *, owner)`: `kind` outside `{"MT", "PT", "HT", "UL"}` or `name`
   without `f"_{kind}_"` with a non-empty prefix and suffix (`[A-Za-z0-9_]`) → `ValueError` with `"does not
   follow"`. Cached by `name`: always the same class (a different kind for a cached name →
   `ValueError`). Class created once: direct subclass of `Menu`/`Panel`/`Header`/`UIList` with
   `bl_idname = bl_label = name`, no-op `draw` (or `draw_item` for `UL`), `bl_space_type =
   "EMPTY"`, `bl_region_type = "WINDOW"` (`PT`) or `"HEADER"` (`HT`) **[I]**, `__module__ =
   "quartz.placeholder"`, `_q_placeholder = True`. If `not registry.is_registered(cls)` (first
   time, or unregistered by `registry.restore`/`unregister_class`) **and**
   `registry.lookup(name, resolve=False)` is `None`, it registers under `registry.owner_scope(owner)`
   (the `owner` of the call that registers applies; the cache does not store an owner); if another registered class
   occupies the RNA name (e.g. an add-on that redefined `VIEW3D_HT_header`), it does NOT register (registering
   would displace that class, §2.5.1 step 4) and returns the unregistered placeholder; returns `cls`.

Errors: `TypeError` (`"expects a Panel, Menu, Header or UIList subclass"`); `AttributeError`
(`"'UILayout' object has no attribute '"`, with `strict_layout`); `ValueError` (`"does not follow"`).

#### 2.5.7 `quartz/utils/__init__.py`

```python
from quartz.utils import previews, units   # submodules
register_class = quartz.registry.register_class; unregister_class = quartz.registry.unregister_class   # same objects
def register_classes_factory(classes: Sequence[type]) -> tuple[Callable[[], None], Callable[[], None]]
def register_submodule_factory(module_name: str, submodule_names: Sequence[str]) -> tuple[Callable[[], None], Callable[[], None]]
escape_identifier = quartz.rna.datapath.escape_identifier; unescape_identifier = quartz.rna.datapath.unescape_identifier   # [O]
def flip_name(name: str, strip_digits: bool = False) -> str
def user_resource(resource_type: str, *, path: str = "", create: bool = False) -> str
def resource_path(type: str, *, major: int | None = None, minor: int | None = None) -> str
def system_resource(type: str, *, path: str = "") -> str
def script_path_user() -> str
def script_paths(*, subdir: str | None = None, user_pref: bool = True, check_all: bool = False, use_user: bool = True,
                 use_system_environment: bool = True) -> list[str]
def script_paths_pref() -> list[str]
def script_paths_system_environment() -> list[str]
def extension_path_user(package: str, *, path: str = "", create: bool = False) -> str
def execfile(filepath: str, *, mod: ModuleType | None = None) -> ModuleType
def time_from_frame(frame: float, *, fps: float | None = None, fps_base: float | None = None) -> datetime.timedelta
def time_to_frame(time: float | datetime.timedelta, *, fps: float | None = None, fps_base: float | None = None) -> float
def smpte_from_frame(frame: float, *, fps: float | None = None, fps_base: float | None = None) -> str
def smpte_from_seconds(time: float, *, fps: float | None = None, fps_base: float | None = None) -> str
def register_manual_map(manual_hook: Callable) -> None
def unregister_manual_map(manual_hook: Callable) -> None
def manual_map() -> Iterator
def manual_language_code(default: str = "en") -> str
def register_preset_path(path: str) -> bool
def unregister_preset_path(path: str) -> bool
def preset_paths(subdir: str) -> list[str]
def preset_find(name: str, preset_path: str, display_name: bool = False, ext: str = ".py") -> str | None
def register_cli_command(id: str, execute: Callable) -> object
def unregister_cli_command(handle: object) -> None
def register_tool(tool_cls: type, *, after: object = None, separator: bool = False, group: bool = False) -> None
def unregister_tool(tool_cls: type) -> None
def keyconfig_init() -> None
def keyconfig_set(filepath: str, *, report: Callable | None = None) -> None    # always raises NotImplementedInQuartz (rule 9)
def load_scripts(*, reload_scripts: bool = False, refresh_scripts: bool = False, extensions: bool = True) -> None
def load_scripts_extensions(*, reload_scripts: bool = False) -> None
def refresh_script_paths() -> None
def modules_from_path(path: str, loaded_modules: set[str]) -> list[ModuleType]
def blend_paths(*, absolute: bool = False, packed: bool = False, local: bool = False) -> list[str]
def is_path_builtin(path: str) -> bool
def is_path_extension(path: str) -> bool
def app_template_paths(*, path: str | None = None) -> Iterator[str]
def make_rna_paths(struct_name: str, prop_name: str, enum_name: str) -> tuple[str, str, str]
def expose_bundled_modules() -> None
```

The 45 public `utils` names from the dump all exist **[O]**; those in `compat/bpy/utils` are these
same objects (identity, §3.1). Rules:

1. `register_classes_factory(classes)`: `register()` calls `register_class` in order;
   `unregister()` calls `unregister_class` in **reverse** order **[L]**; an exception stops at the item and
   propagates.
2. `register_submodule_factory(module_name, names)`: `register()` imports
   `f"{module_name}.{n}"` in order and calls each one's `register()`; `unregister()` calls
   `unregister()` in reverse order and removes those submodules from `sys.modules` **[L]**.
3. `flip_name(name, strip_digits=False)` **[O]** (`"Hand.L"` → `"Hand.R"`, `"left_arm"` →
   `"right_arm"`, `"Foot.R.001"` → `"Foot.L.001"`, `"Foot.R.001"` with `strip_digits=True` →
   `"Foot.L"`): (a) splits off a trailing `"." + digits` suffix; with `strip_digits` it is discarded,
   otherwise it is put back at the end; (b) in the base, if it ends with a separator (`.`, `_`, `-`, space) + a
   side letter (`L`, `R`, `l`, `r`), swaps the letter keeping its case; otherwise, if it starts with a side
   letter + separator, swaps it; otherwise, if it starts or ends with `left`/`right` (cases `left`, `Left`,
   `LEFT` and the equivalents of `right`), swaps the word keeping the case pattern (start before
   end) **[I]**; (c) nothing matched → base unchanged.
4. Paths: `user_resource(t, path=, create=)`: `t` ∈ `{"DATAFILES": datafiles_dir, "CONFIG":
   config_dir, "SCRIPTS": scripts_dir, "EXTENSIONS": extensions_dir}` from `quartz.app.paths`; anything else →
   `PropertyTypeError` with `'enum "'`; returns `os.path.join(str(base), path)` (without `path`, the base);
   `create` → `os.makedirs(exist_ok=True)`. `resource_path(t, major=, minor=)`: the version is resolved
   (`None` → `quartz.app.version[0]`/`[1]`; non-`int` → `TypeError`), but Quartz's layout does not
   have a per-version subfolder, so the result does not depend on it **[I]**: `"USER"` →
   `str(user_dir())`, `"LOCAL"` → `str(PROJECT_ROOT)`, `"SYSTEM"` → `""` **[I]**; any other `t` →
   `PropertyTypeError` with `'enum "'`. `system_resource(t, path=)`: `t` ∈
   `{"DATAFILES", "SCRIPTS", "EXTENSIONS", "PYTHON"}` → `""` (Quartz has no system resources)
   **[I]**; any other `t` → `PropertyTypeError` with `'enum "'`. `script_path_user()` → `str(scripts_dir())`. `script_paths(...)` = `[script_path_user()]`
   (if `use_user`) + `script_paths_pref()` (if `user_pref`) + `script_paths_system_environment()`
   (if `use_system_environment`), without duplicates; with `subdir`, each becomes `join(p, subdir)`;
   without `check_all`, only existing directories **[I]**. `script_paths_pref()` and
   `script_paths_system_environment()` → `[]` (no `BLENDER_*` variable is read) **[I]**.
5. `extension_path_user(package, path=, create=)`: `package` with ≥ 3 parts and 1st part `"bl_ext"`
   or `"qz_ext"` → `str(extensions_dir() / ".user" / repo / pkg)` (+ `path`); any other format →
   `ValueError` **[L]**; `create` creates it.
6. `execfile(filepath, *, mod=None)`: module `mod` or `types.ModuleType("__main__")`, with
   `__file__ = filepath`; during execution `sys.modules["__main__"]` points to it and afterwards returns
   to the previous one (also on error); `exec(compile(text, filepath, "exec"), mod.__dict__)`; an exception
   propagates; returns the module **[L]**.
7. Time (only the two cited values are **[O]**; the formulas are **[I]**): `rate = fps / fps_base`
   (computations in float64); `fps` `None` → `hooks.current_context().scene.render.fps`
   (and `fps_base`, if `None`, from the same `render`) when accessible (any `AttributeError` → default),
   otherwise `24` and `1.0`; `fps` given and `fps_base` `None` → `1.0`. `time_from_frame(f)` =
   `timedelta(seconds=f / rate)` (`str(time_from_frame(48)) == "0:00:02"` at 24 fps **[O]**);
   `time_to_frame(t)` = seconds × `rate` (accepts `timedelta`). `smpte_from_seconds(t)`: sign `"-"`
   if negative; with `t = abs(t)`: `h = int(t // 3600)`, `m = int(t // 60 % 60)`, `s = int(t % 60)`,
   `f = min(int(round((t - int(t)) * rate)), max(math.ceil(rate) - 1, 0))` (rounding never
   produces a frame equal to `rate`); `f"{sign}{h:02d}:{m:02d}:{s:02d}:{f:02d}"`;
   `smpte_from_frame(f)` = `smpte_from_seconds(f / rate)`; `smpte_from_frame(100) == "00:00:04:04"`
   **[O]**.
8. In-memory registries (module lists): `register_manual_map` appends;
   `unregister_manual_map` removes (missing → `ValueError`) **[L]**; `manual_map()` yields
   `hook()` of each one in order **[L]**. `manual_language_code(default="en")`: `lang =
   translations.locale_explode(translations.locale)[0]`; `None`/empty → `default`; otherwise `lang`
   (`"en"` for `en_US`) **[I]**. `register_preset_path(p)` → `True` if it added,
   `False` if it was already there; `unregister_preset_path(p)` → `True` if it removed **[L]**. `preset_paths(subdir)` =
   existing directories `join(base, subdir)` for `base` in `script_paths(subdir="presets")` +
   registered paths, without duplicates **[L]**. `preset_find(name, preset_path, display_name=False,
   ext=".py")`: first file `name + ext` (or, with `display_name`, whose
   `quartz.path.display_name(file) == name`) in `preset_paths(preset_path)`; otherwise `None` **[L]**.
   `register_cli_command(id, execute)` → handle (repeated id → `ValueError`) **[I]**;
   `unregister_cli_command(handle)` (unknown → `ValueError`) **[I]**; nothing executes them in this
   milestone. `register_tool(tool_cls, after=, separator=, group=)` stores the tool (already stored →
   `ValueError` with `"already registered"`); `unregister_tool` removes it (missing → `ValueError`)
   **[I]**; it does not call `register_class`.
9. Honest no-ops: `keyconfig_init`, `load_scripts`, `load_scripts_extensions`,
   `expose_bundled_modules` (Quartz does not load startup scripts). `keyconfig_set` →
   `NotImplementedInQuartz("bpy.utils.keyconfig_set")`. `refresh_script_paths()`: appends to the end
   of `sys.path` each existing `join(p, "modules")` from `script_paths()` that is still absent **[L]**.
   `modules_from_path(path, loaded)`: for each `(name, _)` of `quartz.path.module_names(path)` not in
   `loaded`: `importlib.import_module(name)` (exception → traceback on `stderr`, skip), adds it
   to `loaded`; returns the imported ones **[L]**.
10. `blend_paths(absolute=, packed=, local=)`: non-empty `filepath` values from
    `quartz.session.current().data.images` and `.texts` (lazy import; missing collection skipped),
    in order, without duplicates; `absolute` → `quartz.path.abspath`; `packed` and `local` are accepted and
    ignored (there are no libraries or packing) **[I]**. `is_path_builtin(p)`:
    `quartz.path.is_subdir(p, PROJECT_ROOT/"quartz")` or under `compat_dir()`; `is_path_extension(p)`:
    under any directory of `extension_repos()` or `extensions_dir()/".user"` **[I]**.
    `app_template_paths(path=)`: yields `scripts_dir()/"startup"/"bl_app_templates_user"`(`/path`)
    only if it exists **[I]**. `make_rna_paths(s, p, e)` **[L]**: without `s` → `("", "", "")`; with `s` and
    without `p` → `(s, s, "")`; with `p` → `rna = f"{s}.{p}"`; without `e` → `(rna, rna, "")`; with `e` →
    `enum = f"{rna}:'{e}'"` and `(enum, rna, enum)`.

Errors: `PropertyTypeError` (`'enum "'`); `ValueError` (`extension_path_user`, manual map,
`"already registered"`); `TypeError` (`resource_path` with a non-`int` version);
`NotImplementedInQuartz` (`"bpy.utils.keyconfig_set"`).

#### 2.5.8 `quartz/utils/previews.py`

```python
def new() -> "ImagePreviewCollection"
def remove(pcoll: "ImagePreviewCollection") -> None       # pcoll.close()
class ImagePreviewCollection(dict):                       # name -> ImagePreview
    def new(self, name: str) -> "ImagePreview"
    def load(self, name: str, filepath: str, filetype: str, force_reload: bool = False) -> "ImagePreview"
    def clear(self) -> None
    def close(self) -> None
@builtin_struct
class ImagePreview(Struct):
    icon_id: int                    # rna INT ro (virt -> self._q_icon_id); process counter: unique, >= 1, increasing, never reused
    image_size: tuple[int, int]; icon_size: tuple[int, int]     # rna (INT [2], default (0, 0))
    is_image_custom: bool; is_icon_custom: bool                 # rna (default False)
    image_pixels: list; icon_pixels: list                        # python members ro: [] (nothing decoded)
    q_filepath: str; q_filetype: str                             # python members ro (native; "" for new()), stored in _q_filepath/_q_filetype
    def reload(self) -> None                                     # no-op
```

Rules: `new(name)` with an existing name → `KeyError` with `"already exists"` **[L]**; `load`:
`filetype` outside `("IMAGE", "MOVIE", "BLEND", "FONT")` → `ValueError` **[L]**; existing name without
`force_reload` → `KeyError` with `"already exists"`, with `force_reload` it reuses the entry and
updates `q_filepath`/`q_filetype` **[I]**; the file is never read and does not need to exist. `clear()`
empties it; `close()` = `clear()` (the collection remains usable) **[I]**.

#### 2.5.9 `quartz/utils/units.py`

```python
categories: object   # immutable namespace; each attribute is a str equal to its own name; __iter__ yields the names
systems: object      # same
def to_string(unit_system: str, unit_category: str, value: float, precision: int = 3, split_unit: bool = False,
              compatible_unit: bool = False) -> str
def to_value(unit_system: str, unit_category: str, str_input: str, str_ref_unit: str | None = None) -> float
```

The dump records only the existence of `categories`, `systems`, `to_string` and `to_value` **[O]**; names and
formatting below are **[I]**:

1. `systems`: `NONE`, `METRIC`, `IMPERIAL`. `categories`: `NONE`, `LENGTH`, `AREA`, `VOLUME`,
   `MASS`, `ROTATION`, `TIME`, `TIME_ABSOLUTE`, `VELOCITY`, `ACCELERATION`, `CAMERA`, `POWER`,
   `TEMPERATURE`, `WAVELENGTH`, `COLOR_TEMPERATURE`, `FREQUENCY`. Assigning → `AttributeError`.
   A system or category outside the lists → `ValueError` with `"unknown"`.
2. Number: `f"{v:.{precision}f}"` with no trailing zeros or trailing point (`1.0` → `"1"`, `1.5` → `"1.5"`).
3. Units (factor to the base unit, symbol; `compatible_unit` uses the ASCII symbol in
   parentheses): METRIC LENGTH `km 1e3`, `m 1`, `cm 1e-2`, `mm 1e-3`, `µm 1e-6 (um)`; IMPERIAL LENGTH
   `mi 1609.344`, `ft 0.3048`, `in 0.0254`, `thou 2.54e-5`; METRIC MASS `t 1e3`, `kg 1`, `g 1e-3`,
   `mg 1e-6`; IMPERIAL MASS `lb 0.45359237`, `oz 0.028349523125`; ROTATION (system ≠ `NONE`): value
   in radians shown in degrees `°` (`deg`); TIME (system ≠ `NONE`) `s 1`, `ms 1e-3`. AREA/VOLUME METRIC: `m²`/`m³`
   (`m2`/`m3`) with no scale change. Other combinations and system/category `NONE`: just the number.
4. `to_string` picks the largest unit with `|value| >= factor` (zero → the unit with factor 1) and returns
   `f"{number} {symbol}"`; `split_unit=True` → integer part in the largest unit + remainder in the next
   smaller one, separated by a space, omitting a zero remainder.
5. `to_value`: sum of `number[unit]` terms separated by spaces (`"1m 50cm"` → `1.5`,
   `"90°"`/`"90deg"` in ROTATION → `π/2`); a term without a unit uses `str_ref_unit` (if given) or the
   base unit; invalid input → `ValueError` with `"could not convert"`.

#### 2.5.10 Tests

All in `tests/unit/registry/`, without `quartz.session` and without `quartz.testing` (§2.0.1, rule 4),
except the schema blocks marked "(gate)", which use `quartz.testing.rna_schema_diff`/
`function_signature_diff`, the `blender_dump` fixture and a module-level `DIVERGENCES` (§2.4.5). Each
file defines a local `sandbox` fixture (autouse): `hsnap = hooks.snapshot()`, `ssnap =
settings.snapshot()`, `rsnap = registry.snapshot()`, `registry.install_hooks()`; on exit
`registry.restore(rsnap)`, `settings.restore(ssnap)`, `hooks.restore(hsnap)` (pytest runs these
tests before `tests/unit/rna`, which depend on the default hooks, §2.0.2). Tests that change
`translations.locale` restore it with `set_locale` in a `finally`. Test classes use the class prefix
`QZT_` (operator idnames `qzt.*`, except where an **[O]** fact requires another name) and are
defined inside the tests. Isolation before the siblings exist: nothing here uses names from
`quartz.types` (package) nor imports modules from `l2-idmodel`/`l2-datablocks`; test data are
local registered `PropertyGroup`s and instances created with `_q_new_child`; a fake context via
`hooks.install(current_context=...)` inside the `sandbox`.

- `test_register_rules.py`: each fact of `probes.registration_errors` and `probes.required_bl_attrs`
  reproduced (`quartz.errors` type + fragments from §2.5.1): idname without a dot, uppercase, two
  dots, `_OT_` form, long (`"quartz." + "x" * 80` → message with the 63-character idname and
  `"maximum length is 60"`), leading digit accepted, no `bl_idname` (class name); Operator without
  `bl_label`; Panel missing each required attribute, `bl_space_type="NOPE"` (full list in the message),
  nonexistent `bl_parent_id` (message with the child's RNA name), name outside the convention (registers
  and writes to `stderr` a line with `"'_PT_'"`, `capsys`), Panel with its own `bl_idname` (RNA name =
  `bl_idname`); Menu (without `bl_label`, without `draw`), Header (without `bl_space_type`, without `draw`; without
  `bl_region_type` accepted), UIList and `AddonPreferences` with nothing; several missing required attributes → the
  first in table order; `bl_options` with an invalid item (the first in sorted order) and
  non-set; `bl_space_type=3` and `bl_idname=None` (`"expected a string"`); registering twice;
  another class with the same RNA name replaces the previous one (the old one loses `bl_rna`, its
  `unregister()` runs); unregistering an unregistered class, twice, and a plain class; registering a plain class
  (step 1, `"from 'type' instance"`), non-registrable builtin type (`Event`: step 1) and a base or
  builtin type with a registrable base (`Operator`, `OperatorFileListElement`: step 2,
  `"already registered as a subclass"`); atomic
  registration (prop with `PointerProperty(type=<unregistered PG>)` → `"could not register"`, no
  `bl_rna`, empty `lookup`, `install_properties` undone); judge `register.classmethod_hooks`
  (order `["register", "unregister"]`); `is_registered`/`StructMeta.is_registered`; RNA name
  `"QUARTZ_PROBE_OT_hello"` **[O]**; `operator_rna_name`/`operator_idname_py` round trip and
  `ValueError` (`operator_rna_name("a.b.c") == "A_OT_b.c"`); `validate_operator_idname` directly.
- `test_registry_scope.py`: nested `owner_scope` restored after an exception; `owner_of`,
  `classes_owned_by`, `counts_by_base` (ignores `"quartz.*"`); `type_props_owned_by` with dynamic
  props on a registered `PropertyGroup` (defined, removed with `del`, removed by
  `unregister_class` of the type); without `install_hooks()` nothing is recorded; `subscribe` (events and
  canceller); `iter_classes` (order, filter by base), `iter_operators`, `operator_submodules`,
  `operator_class` in both forms; `lookup` with/without resolver (`set_missing_type_resolver` and
  `resolve=False`); `snapshot`/`restore` undoes registrations, re-registers the removed ones (same
  identity, same owner, `iter_classes` order equal to the snapshot's), restores dynamic props
  (with the owner recorded in the snapshot, not the current one) and UI extensions, without calling
  user `register()`/`unregister()`, and is idempotent; reentrancy (resolver that registers a
  placeholder during `bl_parent_id` validation); `registrable_base_of`, `iter_bases` (order of
  `register_base`, `PropertyGroup` first), `base_callbacks` (unknown → `KeyError`),
  `register_base` with a non-struct → `TypeError`; `rna_name_of` of a registered class, of an unregistered one
  (Panel without `bl_idname` → class name; operator → `"QZT_OT_x"`) and of a plain class (class
  name, no exception); `install_hooks()` twice does not duplicate recordings.
- `test_operator_class.py`: properties class (`__name__`/`bl_rna.identifier` = RNA name,
  props rebuilt including from a mixin and a user parent class, in the order of `_q_installed`,
  owner `P`, strict, removed on unregister, error without registration, unregistered subclass of a
  registered operator → `RegistrationRuntimeError`);
  `_p` shared between `op` and `op.properties`; `q_new_properties` isolated; `_q_assign` with the
  facts of `probes.operator_basic` (`call_bad_kwarg`, `call_bad_enum`, `call_bad_type`,
  `call_out_of_range` clamped, `is_property_set` only for those passed); `as_keywords` (only declared,
  `ignore`); `report` valid/invalid and `has_reports`; `poll_message_set` with text and with a callable
  and `_q_take_poll_message` clearing (a write on one class does not show up in another or in a subclass);
  judge `ops.defaults` (`AttributeError` on missing `bl_*`);
  `name` = `bl_label`; `options` and `macros`; `Event.q_synthetic` (fields, invalid enum, unknown
  field, write → `ReadOnlyError`); `CollectionProperty(type=OperatorFileListElement)` in an
  operator; constants `OPERATOR_OPTIONS`, `REPORT_TYPES`, `EVENT_TYPES`, `EVENT_VALUES`,
  `OPERATOR_RETURN_FLAGS` equal to the dump. (gate) Schema: `rna_schema_diff` of `Operator`
  (`base_classes`), `Event` and `OperatorProperties` (`sub_structs`); `base_callbacks(Operator)` equal
  to `registration.callbacks` (names, `optional`, `classmethod`).
- `test_ui_classes.py`: `append`/`prepend`/`remove`/`is_extended` with the facts of
  `probes.ui_extension_points` (before `False`, after `True`, `draw_sequence` with 2 functions, removing
  twice is silent); order of `draw_sequence` with several `prepend`/`append`; owners by
  `owner_scope`; `draw_funcs_owned_by`, `iter_extended`, `extensions_snapshot/restore`; unregister
  discards extensions; `SPACE_TYPES`/`REGION_TYPES`/`PANEL_OPTIONS`/`MENU_OPTIONS` equal to the dump;
  `UI_UL_list.filter_items_by_name` (with/without `reverse`, empty pattern with and without `flags`, item without the
  prop), `sort_items_helper`, `sort_items_by_name`; `UIList.bitflag_filter_item` read on an instance
  = `1 << 30` and `bitflag_item_never_show` = `1 << 29`; `remove` of a bound method equal;
  `Menu.draw_collapsible`, `draw_preset` (without attributes: nothing), `path_menu` with files in
  `tmp_path` (casefold order, `filter_ext`, `add_operator`); `layout` of a directly created instance =
  `None`. (gate) Schema: `Panel`, `Menu`, `Header`, `UIList`, `PropertyGroup`,
  `AddonPreferences` against `base_classes`; `base_callbacks` of each equal to the dump.
- `test_prefs.py`: `Preferences()` without a session, strict; sub-structs with stable identity;
  `addons.new/remove`, `module` key, `LinkError`; `Addon.preferences` resolving by
  `bl_idname == module` **[O]** (none → `None`; re-registering swaps the instance; last registered
  wins); `PreferencesEdit.undo_steps` ↔ `settings.undo_steps`; `PreferencesView.language` ↔
  `translations.locale` (restored on exit); `temporary_directory` under `qz_user_dir`;
  `extensions.repos` (`user_default` `USER`, `system` `SYSTEM`, `use_remote_url` false; same
  instance across reads) **[O]**; `language` with `"DEFAULT"`; `version` read-only and equal to
  `quartz.app.version`; `themes`/`ui_styles`/`autoexec_paths` empty and stable; `q_reset` (props
  return to default, `addons` empty, `settings.undo_steps` untouched). (gate) Schema: `Preferences`
  and `Addon` (`sub_structs`), with `DIVERGENCES["Preferences.use_preferences_save.default"]` and, if the
  L1 `PropertyDef`s do not express the `is_never_none` flag of the eight pointers to sub-structs,
  an entry `DIVERGENCES["Preferences.<pointer>.flags"]` with the reason for each one.
- `test_inert_bases.py`: for each base in `types.stubs`, a minimal subclass registers and
  unregisters; a missing required attribute from the dump → `MissingClassAttributeError` with the name;
  `base_callbacks` of each base equal to `base_classes[...]["registration"]["callbacks"]` (all
  except `NodeTreeInterfaceSocket`, which is not in the dump and has `{}`); `Macro` in `operator_class`,
  `define`, `_q_assign({})` → `NotImplementedInQuartz("Macro operators")`; `HydraRenderEngine` with its own `bl_rna`
  and `registrable_base_of(sub) is RenderEngine`; `NodeTree` is not an ID (`_q_is_id` false);
  `Space.draw_handler_add/remove` and `draw_handlers` (callback never called; removing an unknown
  handle is silent); the 16 `Space*` classes exist with `bl_rna.identifier` = name and are
  names in `types_names` of the dump.
- `test_uilayout.py`: `UILAYOUT_FUNCTIONS` == `extras.UILayout_functions` (116, order and lists);
  each key of `UILAYOUT_OUTPUTS` is in `UILAYOUT_FUNCTIONS` and its names are in its list;
  `OPERATOR_CONTEXTS` with the 12 values in order;
  for each explicit function, `inspect.signature` == dump list minus `UILAYOUT_OUTPUTS`;
  recorded tree (nesting, normalized kwargs, prop inheritance in the child, `panel` with
  `default_closed`); valid `prop` (PropertyDef, Python descriptor, `'["key"]'`) and invalid
  (`UNKNOWN_PROPERTY`, `note_missing` only for a builtin type, via `hooks.install(note_missing=...)`);
  `operator` returning `q_new_properties()` and recorded assignment; `operator_enum` returns `None`;
  `template_popup_confirm("")` → `None` without an issue; unknown operator (`UNKNOWN_OPERATOR`,
  permissive object, `note_missing("bpy.ops.x.y")`, also with the `"X_OT_y"` form); invalid `prop`
  on an operator properties class does not annotate; unknown `menu`/`popover`;
  `enum_item_name` (missing item and non-enum prop → `""`); `__getattr__`: generic dump function
  (`template_header()` records a node and returns `None`; `operator_menu_hold("qzt.x")` returns the
  properties), unknown name
  (issue and `note_missing("bpy.types.UILayout.<name>")` only when called), `strict_layout=True` →
  `AttributeError`, name with `_` → `AttributeError`; `draw_ui`: false poll, exception in poll, exception
  in `draw` and in an attached function (the others still run, traceback in `stderr`, `ok` false),
  `check_poll=False`, `Panel` header, `operator_context` restored between functions, `TypeError`
  for a non-UI class, `context=None` without a session; `draw_menu`/`draw_panel`; `draw_ui_list` with
  `filter_items` (filter, inverted `neworder`, `bitflag_item_never_show`, wrong size →
  `DRAW_EXCEPTION`), without `draw_item` and with an invalid `propname`; `placeholder_type` (identity,
  `ValueError`, owner, re-registration after `registry.restore`, name taken by a registered user class
  → the user class stays registered and the placeholder does not); `DrawResult.ok`;
  `q_issues` is the same list at the root and in the children.
- `test_utils.py`: identity of `register_class`/`unregister_class`/`escape_identifier`/
  `unescape_identifier`; the 45 `utils` names from the dump present; `register_classes_factory`
  (order and reverse); `register_submodule_factory` with a package in `tmp_path` (restoring
  `sys.path`/`sys.modules`); judge `utils.flip_name`, `utils.escape_identifier`, `utils.smpte`,
  `utils.time_from_frame`; `time_to_frame` with `timedelta`; negative `smpte_from_seconds` and with
  `fps_base`; `fps` read from a fake context (`hooks.install(current_context=lambda:
  SimpleNamespace(scene=SimpleNamespace(render=SimpleNamespace(fps=30, fps_base=1.0))))`) and default 24
  without a context; `smpte_from_seconds(0.99999)` does not produce frame 24 at 24 fps;
  `user_resource`/`resource_path` (with and without `major`/`minor`, same result)/`system_resource`/
  `script_path_user`/`script_paths`/`extension_path_user`/`is_path_builtin`/`is_path_extension`/
  `app_template_paths` with `qz_user_dir` (only paths under `tmp_path`); invalid enum →
  `PropertyTypeError`; `execfile` (restores `__main__` also on error); manual map,
  `manual_language_code()` == `"en"`, presets (`register_preset_path`, `preset_paths`,
  `preset_find` in `tmp_path`), `register_cli_command`, `register_tool`; `make_rna_paths` (four
  forms); `keyconfig_set` → `NotImplementedInQuartz`; no-ops do not raise; `modules_from_path` and
  `refresh_script_paths` with `sys.path` restoration; `blend_paths` with a fake module placed in
  `sys.modules["quartz.session"]` by `monkeypatch.setitem` (whose `current()` returns an object with
  `data.images`/`data.texts` of items with `filepath`; duplicate and empty omitted; missing collection
  skipped) — no real session.
- `test_previews_units.py`: `previews.new/remove`, unique and increasing `icon_id`s,
  `ImagePreviewCollection.new/load` (repeated name, `force_reload`, invalid `filetype`),
  `clear/close`, strict `ImagePreview`, read-only `q_filepath`; `units.systems`/`categories` (names, iteration,
  immutable); `to_string` (unit choice, `precision`, `split_unit`, `compatible_unit`,
  `NONE`, rotation in degrees), `to_value` (sum of terms, `str_ref_unit`, error), round trip
  `to_value(to_string(v)) ≈ v` for METRIC LENGTH.

### 2.6 Runtime: session, context, operators, undo and `.qz` (`l2-runtime`)

Layer 2 integrator: it connects `l2-idmodel`, `l2-datablocks` and `l2-registry-ui` (§2.0.1) and delivers the
single session, the context, operator calls, undo, the `.qz` file and the test helpers.
Normative sequences already fixed in §2.1 (hooks §2.1.1, handlers §2.1.2, state §2.1.5, session
§2.1.7, `ops.call` §2.1.8); this section details them without contradicting them.

**Isolation (§0.6).** So that parts of this task are testable before the siblings exist, the
**module-level** imports are restricted as follows (L2 imports stay inside the functions that use them; they remain
subject to `tests/arch/test_layering.py`):

| Module | Module level | Inside functions |
|---|---|---|
| `quartz/io/qzfile.py` | stdlib, numpy, `quartz.errors` | — |
| `quartz/io/state.py` | stdlib, numpy, `quartz.errors`, `quartz.rna` | `quartz.types.id`, `quartz.types.blenddata`, `quartz.session` |
| `quartz/testing.py` | stdlib, `quartz.errors`, `quartz.rna` | `quartz.session`, `quartz.contexts`, `quartz.registry`, `quartz.app.*`, `quartz.path`, `quartz.types`, `quartz.math.bvhtree`, `quartz.types.mesh`, `quartz.ops` |
| `quartz/contexts.py` | stdlib, `quartz.errors`, `quartz.rna` | `quartz.types.object` |
| `quartz/ops.py` | stdlib, `quartz.errors`, `quartz.app.settings`, `quartz.rna.hooks` | `quartz.registry`, `quartz.session`, `quartz.types.operator`, `quartz.types.stubs` |
| `quartz/io/__init__.py` | stdlib, `quartz.errors`, `quartz._version`, `quartz.io.state`, `quartz.io.qzfile` | `quartz.session`, `quartz.app.*` |
| `quartz/undo.py`, `quartz/session.py` | stdlib, `quartz.errors` | everything else |

None of these modules has an import side effect (§2.0.2): `import quartz.session` does not create the session nor install hooks.

#### 2.6.1 `quartz/session.py`

```python
TEMPLATES: tuple[str, ...] = ("default", "empty")
class Session:
    def __init__(self, _token: object = None) -> None   # only current() passes the internal token; another value -> RuntimeError("use quartz.session.current()")
    data: BlendData            # property ro; stable identity forever
    wm: WindowManager          # property ro; the WindowManager "WinMan" (survives reset)
    preferences: Preferences   # property ro
    context: Context           # property ro (the real context; never the restricted one)
    undo: UndoStack            # property ro
    template: str              # property ro; last applied template ("" until the end of the 1st reset)
    def reset(self, *, template: str = "default") -> None     # sequence of §2.1.7 (detail below)
def current() -> Session
def peek() -> "Session | None"                                # the session if it already exists; creates nothing and installs no hooks
def reset(*, template: str = "default") -> None               # current().reset(template=template)
def api_data() -> "BlendData | RestrictedData"                # target of quartz.data / bpy.data
def api_context() -> "Context | RestrictedContext"            # target of quartz.context / bpy.context
@contextmanager
def restrict_blend(*, enabled: bool | None = None) -> Iterator[None]   # None -> settings.restrict_register; stackable
def is_restricted() -> bool
def build_factory_scene(session: Session) -> None
def build_empty_scene(session: Session) -> None
def install_hooks() -> None
def _q_point_windows(data: BlendData, scene: "Scene | None" = None, *, force: bool = False) -> None   # internal (reset, state.apply, load_qz)
def _q_set_data_version(data: BlendData, version: tuple[int, int, int]) -> None                     # internal (reset, save_qz, load_qz)
```

Rules:

1. **`current()`** calls `install_hooks()` on every call (idempotent). On the first call in the
   process, in this order: `quartz.types.load_builtin_types()`; `s = Session(<internal token>)`;
   creates `BlendData()`, `Preferences()`, `Context(s)`, `UndoStack(s)` and stores them in `s`; creates the
   WindowManager with `WindowManager._q_construct("WinMan")` and links it with
   `data.window_managers._q_link(wm)` (the collection has no `new`, §2.2.10); creates a `RestrictedData(s)`
   and a `RestrictedContext(s)` (stable identity per session: an add-on that captures
   `from bpy import context` at import keeps the restricted one forever **[L]**); stores `s` in the
   module variable (from here on `peek()` and reentrant calls to `current()` — for example, an
   `update` callback fired by scene assembly, via the `current_context` hook — return `s`);
   if `importlib.util.find_spec("quartz.operators")` is not `None`, calls
   `quartz.operators.register_builtin()` (sibling task absent → skip, no error); finally
   `s.reset(template="default")`. If any step raises, the module variable goes back to `None` and
   the exception propagates. Subsequent calls return the same `Session` (D14).
2. **`Session.reset(template)`** executes §2.1.7 in this order: (1) `template ∉ TEMPLATES` →
   `ValueError` with `"unknown template"`; (2) `install_hooks()`; (3)
   `handlers.dispatch("load_pre", "")`; (4) `handlers.clear_non_persistent()`,
   `timers.clear(keep_persistent=True)`, `msgbus.clear()`; (5) `undo.clear()`,
   `context._q_clear_overrides()`, `wm.q_modal_handlers`, `wm.q_fileselect_requests` and
   `wm.q_ui_requests` emptied in place (`lst.clear()`) **[I]**; (6) `data.q_clear(keep=[wm])` and
   `wm._q_trim_windows(1)` (the WM keeps identity and `keyconfigs`; window 0 keeps identity; `wm.operators` is not cleared: there is no API for that in §2.2.10
   **[I]**); (7) `build_factory_scene(self)` or `build_empty_scene(self)`; (8)
   `data.use_autopack = False`, `_q_set_data_version(data, quartz.app.version)`,
   `data.q_set_filepath("")`, `data.q_mark_clean()` (in this order; `is_dirty` is false afterwards) and
   `template` stored; (9) `dispatch("load_factory_startup_post", "")` and `dispatch("load_post", "")`.
   Since (4) runs before (9), only `@persistent` handlers of `load_post` are called **[L]**.
   `preferences` is NOT touched (only `quartz.testing.isolated` calls `q_reset`).
3. **Windows.** The runtime depends on `WindowManager._q_construct` creating the WM with exactly one
   `Window` (§2.2.10: "WinMan" with one `Window`); extra windows (only via `q_new_window`, tests and
   native code) are discarded on reset by `wm._q_trim_windows(1)` (rule 2, step 6). `_q_point_windows(data, scene,
   force)` walks each window of each WM in `data.window_managers` and writes, in this order:
   `scene` (the argument, if not `None`; otherwise the current scene if alive, or the 1st of `data.scenes`, or
   `None`); `view_layer` (`scene.view_layers[0]` if `force` or if the current one is not in
   `scene.view_layers`; `None` without a scene); `screen` and `workspace` (if `force` or if the current one is `None`
   or a tombstone: the 1st alive one in `data.screens`/`data.workspaces`, or `None`). "Tombstone" =
   `getattr(type(x), "_q_removed", False)`. Each write is `setattr(w, name, v)`; if it raises
   `AttributeError` (includes `ReadOnlyError`) and `quartz.rna.get_property(type(w), name)` is a
   `PropertyDef`, it retries with `pdef.write_raw(w, v)` (no callbacks and no dirtying).
4. **`_q_set_data_version(data, v)`**: `pdef = quartz.rna.get_property(type(data), "version")`; if it
   is a `PropertyDef` without `meta["virtual_get"]`, `pdef.write_raw(data, tuple(v))`; otherwise it does nothing
   (the version is derived by the owner, §2.2.5) **[I]**.
5. **`api_data()`/`api_context()`** call `current()` and return `session.data`/`session.context`,
   or the session's `RestrictedData`/`RestrictedContext` when `is_restricted()`. They are evaluated on every
   access of `quartz.data`/`quartz.context` (§1.1.4) and never stored.
6. **`restrict_blend(enabled=None)`**: `None` → `settings.restrict_register` (read on entry).
   Keeps a stack of booleans (pushes on entry, pops in the `finally`); `is_restricted()` is the
   top of the stack (`False` with an empty stack), so an inner `restrict_blend(enabled=False)`
   suspends the restriction only within itself. Only the facades change; `session.context`, the
   `current_context` hook, `update` callbacks and `quartz.ops.call` keep using the real context
   **[L]**.
7. **`install_hooks()`**, idempotent (always passes the same objects: module-level `def` functions,
   never lambdas created at call time): `hooks.install(current_context=_current_context)` with
   `_current_context()` = `current().context`; `quartz.path.set_blend_filepath_provider(_blend_filepath)`
   with `_blend_filepath()` = `current().data.filepath`;
   `quartz.types.set_name_resolver(quartz.registry.lookup)`; `quartz.types.install_hooks()`;
   `quartz.registry.install_hooks()`. It does NOT touch `note_missing` or `repr_root` (§2.1.1, rule 2).

**Factory scene** (`build_factory_scene`; facts from `blender_facts_judge.json` `factory` and from the dump
`factory_scene`). It creates via the public API and explicitly writes each value in the table, even if
it matches the type's default, in this row order:

| Item | How and values |
|---|---|
| `Scene` | `data.scenes.new("Scene")`; `frame_start=1`, `frame_end=250`, `frame_current=1` **[O]**; `render.engine="BLENDER_EEVEE"` **[O]**, `resolution_x=1920`, `resolution_y=1080`, `resolution_percentage=100`, `fps=24` **[O]**; `unit_settings.system="METRIC"` **[O]**; `cursor.location=(0,0,0)` **[O]** |
| `ViewLayer` | if `scene.view_layers` is empty, `scene.view_layers.new("ViewLayer")`; otherwise `view_layers[0].name = "ViewLayer"` **[O]** |
| `Collection` | `data.collections.new("Collection")` linked into `scene.collection.children` **[O]**; `view_layer.active_layer_collection` = the item of `view_layer.layer_collection.children` whose `.collection` is it (`context.collection.name == "Collection"` **[O]**) |
| `Material` | `data.materials.new("Material")`, `diffuse_color=(0.8,0.8,0.8,1.0)` **[O]**; 1 user (via mesh) **[O]** |
| `Dots Stroke` | `data.materials.new("Dots Stroke")`; `is_grease_pencil=True` via `get_property(Material, "is_grease_pencil").write_raw(...)` (read-only prop; `create_gpencil_data` is NI); 0 users **[O]** |
| `Cube` mesh | `data.meshes.new("Cube")`; `from_pydata(cube_verts, cube_edges, cube_faces)` with the exact lists from the judge (explicit edges first, §1.5.2 ⇒ edge order equal to the judge's) and `shade_flat=True` (`sharp_face` all true; `use_smooth` all false **[O]**); `layer = uv_layers.new(name="UVMap")` and `layer.data.foreach_set("uv", uvs)` with the 48 coordinates below, in corner order; `materials.append(Material)` |
| `Cube` UVs | per face, in corner order: f0 `(.625,.5) (.875,.5) (.875,.75) (.625,.75)` **[O]** (`uv_first4`); f1 `(.375,.75) (.625,.75) (.625,1) (.375,1)`; f2 `(.375,0) (.625,0) (.625,.25) (.375,.25)`; f3 `(.125,.5) (.375,.5) (.375,.75) (.125,.75)`; f4 `(.375,.5) (.625,.5) (.625,.75) (.375,.75)`; f5 `(.375,.25) (.625,.25) (.625,.5) (.375,.5)` **[I]** (consistent at the seams) |
| `Camera` camera | `data.cameras.new("Camera")`: `type="PERSP"`, `lens=50`, `sensor_width=36`, `clip_start=0.1`, `clip_end=100` **[O]** |
| `Light` light | `data.lights.new("Light", "POINT")`: `energy=1000`, `shadow_soft_size=0.1`, `color=(1,1,1)` **[O]** |
| `World` | `data.worlds.new("World")`, `color=(0.050876,)*3` **[O]**; `scene.world = World` **[O]** |
| objects | `data.objects.new(name, data)` and `Collection.objects.link` in this order: `Cube` (origin), `Light` (loc `(4.076245307922363, 1.0054539442062378, 5.903861999511719)`, rot `(0.650328, 0.055217, 1.866391)`), `Camera` (loc `(7.358891487121582, -6.925790786743164, 4.958309173583984)`, rot `(1.109319, 0.0, 0.814928)`) **[O]**; scale 1, `rotation_mode="XYZ"` |
| selection | `scene.camera = Camera` **[O]**; `view_layer.objects.active = Cube`; `Cube.select_set(True, vl)`, others `select_set(False, vl)` (`selected == ["Cube"]` **[O]**) |
| UI | `Screen` and `WorkSpace` `"Layout"` **[O]** via `_q_construct("Layout")` + `data.screens._q_link`/`data.workspaces._q_link` (no `new`); `_q_point_windows(data, scene, force=True)` (rule 3) |

Declared divergences: no `Render Result`/`Viewer Node` images, `Palette`, `LineStyle`, nor the
other 10 screens/workspaces; the mesh does not have the `.uv_select_*` attributes of the dump.

`build_empty_scene`: `Scene "Scene"` with the same scene settings as the 1st row of the table, `ViewLayer
"ViewLayer"`, only the master collection (`active_layer_collection` = `view_layer.layer_collection`), no
objects, no `World` (`scene.world is None`), `scene.camera is None`, `Screen`/`WorkSpace
"Layout"` and `_q_point_windows(data, scene, force=True)` **[I]**.

Errors: `ValueError` `"unknown template"`; `RuntimeError` `"use quartz.session.current()"`.

#### 2.6.2 `quartz/contexts.py`

```python
__all__ = ("Context", "CONTEXT_MEMBERS", "CONTEXT_METHODS", "NONE_MEMBERS", "providers",
           "register_provider", "unregister_provider")   # required by §2.2.1, rule 2 (BUILTIN_TYPE_MODULES)
CONTEXT_MEMBERS: tuple[str, ...]      # the 71 `context` members of the dump without the 4 methods, alphabetical order [O]
CONTEXT_METHODS: tuple[str, ...] = ("copy", "evaluated_depsgraph_get", "path_resolve", "temp_override")
NONE_MEMBERS: tuple[str, ...]         # the 42 members without a real provider (table below), alphabetical order
Provider = Callable[["Context"], object]
def providers() -> Mapping[str, Provider]                 # live MappingProxyType
def register_provider(name: str, fn: Provider) -> None     # native; replaces or adds; name not an identifier or with leading "_" -> ValueError
def unregister_provider(name: str) -> None                 # name in CONTEXT_MEMBERS -> goes back to the default provider; native -> removes; absent -> KeyError
def _q_providers_snapshot() -> object                      # internal (testing.isolated)
def _q_providers_restore(snap: object) -> None             # internal; restores content and order
@builtin_struct(identifier="Context")
class Context(Struct):
    _q_strict_attrs = True
    def __init__(self, session: object) -> None            # only stores the session in `_q_session`; `.data/.wm/.preferences` are read on each access (duck typing)
    def __getattr__(self, name: str) -> object
    def __setattr__(self, name: str, value: object) -> None
    def temp_override(self, **members: object) -> ContextManager["Context"]
    def copy(self) -> dict[str, object]
    def path_resolve(self, path: str, coerce: bool = True) -> object
    def evaluated_depsgraph_get(self) -> "Depsgraph"
    def _q_clear_overrides(self) -> None                   # internal (Session.reset, load_qz, testing.isolated)
class RestrictedContext:
    def __init__(self, session: object) -> None
    window_manager: WindowManager; preferences: Preferences   # properties -> session.wm / session.preferences
    def __getattr__(self, name: str) -> NoReturn            # RestrictedAccessError
    def __setattr__(self, name: str, value: object) -> None  # "_..." -> object.__setattr__; rest -> RestrictedAccessError
class RestrictedData:
    def __init__(self, session: object) -> None
    def __getattr__(self, name: str) -> NoReturn            # RestrictedAccessError
    def __setattr__(self, name: str, value: object) -> None  # same
```

Rules:

1. `Context` does not declare `PropertyDef` (members do not appear in `bl_rna.properties`; §2.4.4 only
   compares names). Internal state lives in `_q_*` attributes (`_q_session`, `_q_stack: list[dict]`). No
   member collides with a `Struct` attribute (§1.6.7), so all of them reach `__getattr__`.
2. **Resolution** `__getattr__(name)` (only what is not a normal attribute gets here): a name starting with
   `"_"` → `AttributeError`; if `name in providers()`: walks the override stack from the top to the
   base and returns the first value given for `name` (even `None`); otherwise calls the provider with the
   `Context` itself (which already applies the overrides). A `name` outside `providers()` →
   `AttributeError(f"'Context' object has no attribute '{name}'")`, even if it was passed to
   `temp_override` (accepted and invisible **[O]**). Exceptions raised by a provider propagate.
3. **Write**: `__setattr__` with a name starting with `"_"` → `object.__setattr__`; member →
   `ReadOnlyError(f'bpy_struct: attribute "{name}" from "Context" is read-only')` **[O]**; any
   other name → the same message **[I]**.
4. **Default providers** (`ctx` = the `Context`; `session` = `ctx._q_session`). Every provider is
   `None`-safe: if a link in the chain (`window`, `scene`, `view_layer`, active) is `None`, it returns `None`
   (list members return `[]`).

| Member | Value |
|---|---|
| `window_manager` / `blend_data` / `preferences` | `session.wm` / `session.data` / `session.preferences` |
| `window` | `session.wm.windows[0]`, or `None` with no windows; not `None` in the factory **[O]** |
| `screen`, `workspace`, `scene`, `view_layer` | the attribute of the same name on `ctx.window` (`"Layout"`, `"Layout"`, `"Scene"` **[O]**) |
| `tool_settings` / `engine` | `ctx.scene.tool_settings` / `ctx.scene.render.engine` (`"BLENDER_EEVEE"` **[O]**) |
| `layer_collection` / `collection` | `ctx.view_layer.active_layer_collection` / `ctx.layer_collection.collection` (`"Collection"` **[O]**) |
| `active_object`, `object` | `ctx.view_layer.objects.active` (`"Cube"` **[O]**) |
| `mode` | `"OBJECT"` if `ctx.active_object is None` (without importing anything); otherwise `quartz.types.object.context_mode_for(ctx.active_object)` (`"OBJECT"`; `"EDIT_MESH"` in edit mode **[O]**) |
| `edit_object` | `ctx.active_object` if `ctx.active_object.mode == "EDIT"`, otherwise `None` **[O]** |
| `sculpt_object`, `vertex_paint_object`, `weight_paint_object`, `image_paint_object`, `particle_edit_object`, `pose_object` | the active object if the active object's `mode` is `SCULPT`/`VERTEX_PAINT`/`WEIGHT_PAINT`/`TEXTURE_PAINT`/`PARTICLE_EDIT`/`POSE`, otherwise `None` |
| `selected_objects`, `selected_editable_objects` | new list of the objects in `ctx.view_layer.objects` with `select_get(ctx.view_layer)`, in view layer order (factory: 1 **[O]**) |
| `visible_objects`, `editable_objects` | same with `visible_get(ctx.view_layer)` (factory: 3 **[O]**) |
| `selectable_objects` | visible ones with `not hide_select` (factory: 3 **[O]**) |
| `objects_in_mode` | active with `mode != "OBJECT"`: the active object first, then the other objects of the view layer with the same `mode` and `type`, in view layer order **[I]** (`[Cube]` in edit mode **[O]**); otherwise `[]` (factory **[O]**) |
| `objects_in_mode_unique_data` | `objects_in_mode` without repeated `data` (1st occurrence) |
| `NONE_MEMBERS` (42: `active_action`, `active_annotation_layer`, `active_bone`, `active_editable_fcurve`, `active_nla_strip`, `active_nla_track`, `active_operator`, `active_pose_bone`, `active_strip`, `annotation_data`, `annotation_data_owner`, `area`, `asset`, `asset_library_reference`, `editable_bones`, `editable_fcurves`, `gizmo_group`, `grease_pencil`, `property`, `region`, `region_data`, `region_popup`, `selected_bones`, `selected_editable_actions`, `selected_editable_bones`, `selected_editable_fcurves`, `selected_editable_keyframes`, `selected_editable_strips`, `selected_movieclip_tracks`, `selected_nla_strips`, `selected_pose_bones`, `selected_pose_bones_from_active_object`, `selected_strips`, `selected_visible_actions`, `selected_visible_fcurves`, `sequencer_scene`, `space_data`, `strips`, `ui_list`, `visible_bones`, `visible_fcurves`, `visible_pose_bones`) | `None` (41 of them are `None` in headless **[O]**); `asset_library_reference` also calls `hooks.note_missing("bpy.context.asset_library_reference")` on every read (in Blender it is not `None` **[O]**: divergence) |

5. **`temp_override(**members)`** returns a context manager: on entry it pushes a new `dict`
   with `members` (without validating names or types **[I]**) and returns the `Context` itself; on exit
   (also by exception) it removes **that** frame (by identity), wherever it is in the stack; if the
   frame is no longer in the stack (emptied by `_q_clear_overrides`, e.g. `wm.read_factory_settings`
   or `wm.open_mainfile` called inside `context.temp_override(...)`), the exit is silent.
   Nesting combines frames (the innermost wins) **[O]** (`active_object` inside the override =
   `Camera`, then goes back to `Cube`). `window=` changes the base of the derived providers (because they read
   `ctx.window`).
6. **`copy()`** → new `dict` with one key per name in `providers()` (order: `CONTEXT_MEMBERS`,
   then the native ones in registration order), value = `getattr(self, name)` with overrides; without the
   methods **[O]** (keys in alphabetical order **[O]**); unknown keys from `temp_override` are not
   included.
7. **`path_resolve(path, coerce=True)`**: `quartz.rna.datapath.parse(path)`; the 1st token MUST be
   `ATTR` with a name in `providers()` (otherwise `ValueError(f'Path "{path}" could not be resolved')`); with no
   remainder → the member's value; with a remainder (`r = datapath.format(remainder)`) → `value.path_resolve(r,
   coerce)` if the value has that method, otherwise `datapath.resolve(value, r, coerce=coerce)`
   **[O][L]**; `path_resolve("scene.frame_current") == 1` in the factory **[O]**; any `ValueError`
   or `AttributeError`/`KeyError`/`IndexError` along the path → `ValueError` with the full `path`.
8. **`evaluated_depsgraph_get()`** → `dg = self.view_layer.depsgraph; dg.update(); return dg`
   **[I]** (dispatches `depsgraph_update_pre/post` only if something changed, §2.1.2); `view_layer is None` →
   `RuntimeError` with `"no view layer"` **[I]**.
9. **Restricted** (RestrictBlend, D13): `RestrictedContext` exposes only `window_manager` and
   `preferences`; `RestrictedData` exposes nothing. Any other attribute that does not start with `"_"`
   → `RestrictedAccessError(f"'{type(self).__name__}' object has no attribute '{name}'")` **[L]**
   (absent names with `"_"` → plain `AttributeError`); writing a name without `"_"` (including
   `window_manager`) → `RestrictedAccessError` with the same form.

Errors: `ReadOnlyError` `'from "Context" is read-only'`; `AttributeError` `"has no attribute"`;
`ValueError` `"could not be resolved"`; `RuntimeError` `"no view layer"`; `RestrictedAccessError`
`"has no attribute"`; `ValueError` (`register_provider`); `KeyError` (`unregister_provider`).

#### 2.6.3 `quartz/ops.py`

```python
EXEC_CONTEXTS: tuple[str, ...] = ("INVOKE_DEFAULT", "INVOKE_REGION_WIN", "INVOKE_REGION_CHANNELS", "INVOKE_REGION_PREVIEW",
                                  "INVOKE_AREA", "INVOKE_SCREEN", "EXEC_DEFAULT", "EXEC_REGION_WIN", "EXEC_REGION_CHANNELS",
                                  "EXEC_REGION_PREVIEW", "EXEC_AREA", "EXEC_SCREEN")   # items of the context enum in the dump [O]
def call(idname: str, *args: object, **kwargs: object) -> set[str]      # §2.1.8 [O]
def poll(idname: str, exec_context: str = "EXEC_DEFAULT") -> bool
class OpCallable:
    def __init__(self, submodule: str, name: str) -> None
    def __call__(self, *args: object, **kwargs: object) -> set[str]     # call(self.idname_py(), *args, **kwargs)
    def poll(self, *args: object) -> bool                               # 0 or 1 positional str -> poll(idname_py, exec_context); otherwise -> ExecContextError
    def idname(self) -> str             # registry.operator_rna_name(idname_py) — does not require registration [O]
    def idname_py(self) -> str          # f"{submodule}.{name}"
    def get_rna_type(self) -> RNAStruct # operator_class(...).q_properties_class().bl_rna; absent -> OperatorNotFoundError
    bl_options: set[str]                # property; set(cls.bl_options) or {"REGISTER"} without the attribute [I]; absent -> OperatorNotFoundError
    def __repr__(self) -> str           # f"<{P}.ops.{idname_py}>" [I]
class OpsSubmodule:
    def __init__(self, name: str) -> None
    def __getattr__(self, name: str) -> OpCallable     # name with leading "_" -> AttributeError; otherwise always an OpCallable [O]
    def __dir__(self) -> list[str]                     # names (the part after the ".") of the registered operators of this submodule, sorted
def submodule(name: str) -> OpsSubmodule               # cached by name (same instance); not an identifier or leading "_" -> AttributeError
def submodule_names() -> list[str]                     # quartz.registry.operator_submodules()
def __getattr__(name: str) -> OpsSubmodule             # quartz.ops.<mod> -> submodule(name) (includes the AttributeError for "__path__" etc.)
def __dir__() -> list[str]                             # sorted(submodule_names() ∪ public names of the module)
# ---- internals (consumed by quartz.testing) ----
def _q_call(idname: str, *, exec_context: str = "EXEC_DEFAULT", undo: bool | None = None,
            props: Mapping[str, object] | None = None, force_invoke: bool = False,
            event: "Event | None" = None, post: bool = True) -> tuple[set[str], "Operator"]   # steps 2–8 and, if post, 9
def _q_check_return(value: object) -> set[str]                       # step 7; returns a new set
def _q_emit_reports(op: "Operator", start: int = 0) -> int           # step 8 over op._q_reports[start:]; returns len(op._q_reports)
def _q_post(cls: type, op: "Operator", ret: set[str], *, undo: bool | None) -> None   # step 9
```

`P` = `quartz.app.settings.settings.api_prefix`, read at the time of the message. Real attributes of the
module (`call`, `poll`, `submodule`, …) win over `__getattr__`; a submodule with such a name remains
accessible via `submodule(name)`. `OpsSubmodule.__getattr__` MAY cache the `OpCallable`s; tests MUST NOT
depend on their identity.

`call(idname, *args, **kwargs)` = §2.1.8, with these details:

1. **Positionals**: each one is a `str` (execution context, at most one) or a `bool` (`undo` flag, at
   most one), in any order **[I]**; `dict`, another type, a repetition or more than two →
   `ExecContextError("1-2 args execution context is supported")` **[O]**; a `str` outside
   `EXEC_CONTEXTS` → `PropertyTypeError(f"expected a string enum in ({list})")` with `list =
   ", ".join(repr(c) for c in EXEC_CONTEXTS)` **[I]**. Default: `"EXEC_DEFAULT"`, `undo=None`. Then
   `return _q_call(idname, exec_context=..., undo=..., props=kwargs)[0]`.
2. Class: `cls = quartz.registry.operator_class(idname)`; `None` →
   `hooks.note_missing(f"bpy.ops.{idname}")` (always with the Blender name) and
   `OperatorNotFoundError(f'Calling operator "{P}.ops.{idname}" error, could not be found')` **[O]**.
   `cls` a subclass of `quartz.types.stubs.Macro` → `NotImplementedInQuartz("Macro operators")`
   (§2.5.5).
3. `ctx = quartz.session.current().context` (the real one, even under `restrict_blend`) **[L]**.
4. **Poll** once, before the kwargs **[O]** (divergence 2 of ARCHITECTURE §13: Blender calls it
   twice). "The class has X" = some item of `cls.__mro__` before `quartz.types.operator.Operator`
   has `X` in its own `__dict__` (same rule for `poll`, `execute`, `invoke`, `modal`). If it has
   `poll`: `ok = bool(cls.poll(ctx))`; exception → traceback on `stderr` and `ok = False` **[I]**; then,
   always, `msg = cls._q_take_poll_message()` (consumes the message, even with `ok`). `not ok` →
   `PollFailedError(f"Operator {P}.ops.{idname}.poll() {msg or 'failed, context is incorrect'}")`
   **[O]**.
5. `op = cls()`; `op._q_assign(props or {})` (messages with `"Converting py args to operator
   properties:"`, unknown kwarg with `':: keyword "{k}" unrecognized'` **[O]**; out of range
   clamped **[O]**; these errors propagate without wrapping).
6. **Execution**, in this order: if (`force_invoke` or (`exec_context.startswith("INVOKE")` and
   `settings.invoke_in_background`)) and the class has `invoke` → `r = op.invoke(ctx, event or
   Event.q_synthetic())`; otherwise, if it has `execute` → `r = op.execute(ctx)` (also with
   `INVOKE_DEFAULT` in the headless default **[O]**); otherwise, if it has `invoke` → `invoke` as above; otherwise
   `r = {"CANCELLED"}` **[I]**. An exception raised by user code (including by
   nested calls to `quartz.ops`) → `OperatorFailedError("Error: Python: " + traceback.format_exc())` with
   `__cause__` = the exception **[O]**.
7. **Return** (`_q_check_return`): `None` → `OperatorFailedError` with `"incompatible return
   value"` and `"expected a set, not a NoneType"`; non-`set`/`frozenset` → same with `f"expected a set,
   not a {type(r).__name__}"`; an item that is not a `str` in `OPERATOR_RETURN_FLAGS` → same with
   `f"'{v}' not found in ("` + the list of the five in the order of the dump **[O]**.
8. **Reports** (`_q_emit_reports`, `op._q_reports` in order): those without an `ERROR*` type go to
   `sys.stdout` as `f"{T.capitalize()}: {message}"`, `T` = the first type of the report in the order
   of `REPORT_TYPES` **[I]**; then, if there is any `ERROR*` → `OperatorFailedError("Error: " +
   "\n".join(error messages))` (**[O]** with `CANCELLED`, **[I]** with `FINISHED`), before step
   9. `_q_emit_reports` does not alter `op._q_reports`.
9. **Post** (`_q_post`), only with `"FINISHED"` in the return: `bl_options = set(getattr(cls,
   "bl_options", {"REGISTER"}))` **[I]**; if `"UNDO" in bl_options` and `session.undo.enabled` and
   `undo is not False` → `session.undo.push(getattr(cls, "bl_label", idname))`; if `"REGISTER" in
   bl_options` → `session.wm.q_push_operator(op)`.
10. `_q_call` returns `(new set, op)` (never the object returned by the user); `call` returns only the
    `set`.

`poll(idname, exec_context)`: non-`str` `exec_context` → `ExecContextError` (same message);
a `str` outside `EXEC_CONTEXTS` → `PropertyTypeError` as in step 1; absent class →
`OperatorNotFoundError` (same message, same annotation); without `poll` → `True`; otherwise
`bool(cls.poll(ctx))` (exception → traceback on `stderr` and `False`); always calls
`cls._q_take_poll_message()` and discards the value.

Nested calls (an operator that calls `quartz.ops` inside `execute`) use the same `ctx` and have
no special handling.

Errors: `ExecContextError` `"1-2 args execution context is supported"`; `PropertyTypeError`
`"expected a string enum in ("`, `"Converting py args to operator properties:"`;
`OperatorNotFoundError` `"could not be found"` with `f"{P}.ops.{idname}"`; `PollFailedError`
`".poll() "`, `"failed, context is incorrect"`; `OperatorFailedError` `"Error: Python: "`,
`"incompatible return value"`, `"not found in ("`, `"expected a set, not a NoneType"`, `"Error: "`;
`NotImplementedInQuartz` `"Macro operators"`; `AttributeError` (`submodule`).

#### 2.6.4 `quartz/undo.py`

```python
class UndoStack:
    def __init__(self, session: "Session") -> None
    enabled: bool                       # property ro; False on creation and after clear() [O]
    def push(self, message: str = "") -> None
    def undo(self) -> bool
    def redo(self) -> bool
    def can_undo(self) -> bool          # index() > 0
    def can_redo(self) -> bool          # 0 <= index() < len(history()) - 1
    def history(self) -> list[str]      # messages of the steps, from oldest to newest (new list)
    def index(self) -> int              # current step; -1 when empty
    def jump(self, index: int) -> bool
    def clear(self) -> None
```

Rules (memfile style, D15):

1. Each step is `(message, quartz.io.state.capture(session.data))` — the state **after** the action;
   `include_ui=False`: WindowManager, Screen and WorkSpace are left out (§2.1.5(7)).
2. `push(message)`: turns on (`enabled = True`); discards the steps after `index()`; appends; `index()` =
   last; while there are more than `max(settings.undo_steps, 0) + 1` steps, discards the oldest
   (and decrements `index()`) **[I]**. The first `push` (`ed.undo_push`) creates the initial step: right
   after it `can_undo()` is false.
3. `undo()`: without `can_undo()` → `False` without dispatching anything. Otherwise `dispatch("undo_pre", scene)`;
   `index -= 1`; `quartz.io.state.apply(session.data, step_state)` (which re-points the windows,
   §2.6.6 rule 4.6); `dispatch("undo_post", scene)`; `True`. `scene` =
   `session.wm.windows[0].scene` read at the time of each dispatch (or `None` with no windows) **[I]**.
4. `redo()`: mirror with `can_redo()`, `index += 1` and `redo_pre`/`redo_post`.
5. `jump(index)`: outside `[0, len)` → `False`; equal to the current one → `True` with no effect; lower → applies the
   target with `undo_pre`/`undo_post`; higher → `redo_pre`/`redo_post` (one pair of dispatches per jump).
6. Identity preserved: the same Python objects return to the state; IDs removed after the step
   are revived (`ID._q_revive`); IDs created after the step become tombstones, without cascade (§2.1.5(7)). The
   stored state is not altered by `apply` (it can be reapplied).
7. `clear()`: empties, `index() == -1`, `enabled = False`. Called by `Session.reset` and
   `load_qz`.

No errors of its own (an `apply` failure propagates; the already-moved index is not restored **[I]**).

#### 2.6.5 `quartz/io/__init__.py`

```python
QZ_FORMAT: str = "quartz.qz"
QZ_FORMAT_VERSION: int = 1
def save_qz(filepath: str | os.PathLike, *, session: "Session | None" = None, copy: bool = False) -> None
def load_qz(filepath: str | os.PathLike, *, session: "Session | None" = None) -> None
def read_manifest(filepath: str | os.PathLike) -> dict
from quartz.io import state, qzfile     # submodules (no import side effect)
```

Rules (`path = os.path.abspath(os.fspath(filepath))`; `s = session or quartz.session.current()`):

1. A `.blend` suffix (case-insensitive) in `save_qz`/`load_qz` → `FileFormatError` with
   `"'.blend' files are not supported"` before any dispatch (D16); any other extension is
   accepted.
2. `save_qz`: `dispatch("save_pre", path)`; then, inside a `try`: `st = state.capture(s.data)`;
   `doc, arrays = state.encode(st)`; manifest `{"format": QZ_FORMAT, "format_version":
   QZ_FORMAT_VERSION, "quartz_version": quartz._version.__version__, "author": quartz._version.AUTHOR,
   "ids": len(st.ids)}`; `qzfile.write_container(path, manifest, doc, arrays)`. Exception →
   `dispatch("save_post_fail", path)` and re-raises. Success: if `not copy`,
   `s.data.q_set_filepath(path)`, `_q_set_data_version(s.data, quartz.app.version)` and
   `s.data.q_mark_clean()` (with `copy=True` neither `filepath` nor `is_dirty` change **[I]**);
   `dispatch("save_post", path)`.
3. `load_qz`: `dispatch("load_pre", path)`; inside a `try`, **validation phase** (nothing changes in the
   session): `manifest, doc, arrays = qzfile.read_container(path)`; manifest check (rule 4);
   `st = state.decode(doc, arrays)`; `len(st.ids) != manifest["ids"]` → `FileFormatError`
   `"invalid manifest"`; `state.validate(st)`. **Apply phase**: steps (4) and (5) of
   `Session.reset` (`clear_non_persistent` **[L]**, `timers.clear(keep_persistent=True)`,
   `msgbus.clear()`, `s.undo.clear()`, WM overrides and requests emptied) **[I]**;
   `state.apply(s.data, st)` (the UI IDs stay: the state does not have them);
   `_q_point_windows(s.data, s.data.scenes[0] if len(s.data.scenes) else None, force=True)`;
   `s.data.use_autopack` comes from `extra` (applied by `state.apply`);
   `_q_set_data_version(s.data, manifest version)`; `s.data.q_set_filepath(path)`;
   `s.data.q_mark_clean()`; `dispatch("load_post", path)`. An exception at any point after
   `load_pre` → `dispatch("load_post_fail", path)` and re-raises; a failure in the validation phase leaves the
   session intact (same IDs, names, `filepath`, `is_dirty`, undo and handlers).
4. `read_manifest(path)`: `read_container` and returns a copy of the manifest, after validating:
   `format != QZ_FORMAT` → `FileFormatError` `"not a Quartz .qz file"`; `format_version` not an `int`
   (or a `bool`) or `< 1`, `quartz_version` that does not match `^\d+\.\d+\.\d+$`, or `ids` not an `int` ≥ 0 →
   `FileFormatError` `"invalid manifest"`; `format_version > QZ_FORMAT_VERSION` → `FileFormatError`
   `"newer format version"`. "Manifest version" = `tuple(int(x) for x in
   quartz_version.split("."))`. `load_qz` uses the same validation.

Errors: `FileFormatError` `"'.blend' files are not supported"`, `"not a Quartz .qz file"`,
`"invalid manifest"`, `"newer format version"` (and those of §2.6.6/§2.6.7, which propagate).

#### 2.6.6 `quartz/io/state.py`

```python
STATE_VERSION: int = 1
UI_ID_TYPES: tuple[str, ...] = ("WINDOWMANAGER", "SCREEN", "WORKSPACE")   # outside undo and the .qz by default
@dataclass
class IDState:
    rna_type: str; id_type: str; name: str; schema: int; state: dict; instance: "ID | None"
@dataclass
class SceneState:
    ids: list[IDState]; extra: dict
@dataclass(frozen=True)
class IDIndex:                 # not-yet-resolved reference coming from decode: index into SceneState.ids
    index: int
def capture(data: "BlendData", *, include_ui: bool = False) -> SceneState
def apply(data: "BlendData", state: SceneState) -> None
def validate(state: SceneState) -> None        # phase 0 of apply, exposed for load_qz
def encode(state: SceneState) -> tuple[dict, dict[str, np.ndarray]]
def decode(doc: Mapping[str, object], arrays: Mapping[str, np.ndarray]) -> SceneState
```

1. **`capture`**: for each `id` in `data.q_iter_ids()` (fixed order, §2.1.5(6)), skipping
   `id.id_type in UI_ID_TYPES` unless `include_ui`: `IDState(rna_type=type(id).bl_rna.identifier,
   id_type=id.id_type, name=id.name, schema=type(id).q_schema_version, state=copy(id._q_state_get()),
   instance=id)`. `copy` is deep: `dict`/`list`/`tuple`/`set`/`frozenset` are recreated (same
   type), `np.ndarray` is copied, ID instances are kept by reference, scalars are left as they are. Embedded
   IDs (master collection) come inside the owner's state. `extra = {"use_autopack":
   data.use_autopack}`.
2. **Class of an `IDState`**: `base = id_type_info(id_type).cls`; the class is `base` or the subclass
   (recursive search in `__subclasses__`, ignoring classes with `_q_removed`) whose
   `bl_rna.identifier == rna_type` (e.g. `PointLight`); no match → `base` **[I]**.
3. **`validate`** (no side effects): `id_type_info(id_type)` `None` → `FileFormatError` `"unknown ID
   type"`; `schema > cls.q_schema_version` → `FileFormatError` `"newer schema"` (§2.1.5(4)); names
   repeated within the same `id_type` → `FileFormatError` `"duplicate ID name"`; `IDIndex` outside
   `[0, len(ids))` at any depth → `FileFormatError` `"invalid ID reference"`.
4. **`apply(data, state)`**, in this order (the `SceneState` is only changed in `IDState.instance`, rule
   4.2; the state dicts are never mutated — `apply` works on copies):
   1. `validate(state)`; for each `IDState` with `schema < cls.q_schema_version`, `st =
      cls.q_upgrade(st, v)` for `v = schema, schema+1, …, version−1` (chained), without touching `data`.
   2. **Removal**: `has_ui` = some `IDState` with `id_type ∈ UI_ID_TYPES`. Every live ID in
      `data.q_iter_ids()` that is not the `instance` (by identity) of any `IDState` — and, without
      `has_ui`, is not a UI one — is removed, without cascade and without undoing references:
      `data.q_collection_for(id)._q_unlink(id)`, `id._q_main = None`, `id._q_tombstone()`; if `id`
      is a `Scene`, its master collection is also tombstoned (`id.collection._q_tombstone()`, read before the
      scene's tombstone; §2.2.5, rule 4).
   3. **Instances** (in the order of `state.ids`): `instance` not `None` → `ID._q_revive(instance)` (no-op
      if alive; for `Scene`, `ID._q_revive` also on the master, as in §2.2.8, rule 10) and, if the class from rule 2 differs from `type(instance)` (e.g. `light.type` changed after the
      step), `instance.__class__ = class` (keeps `_p`); `instance is None` →
      `class._q_construct(name)` with the final name, stored in `IDState.instance`.
   4. **Linking, 1st phase**: (a) every linked instance (`_q_main is not None`) whose current `name`
      differs from the state's name is unlinked (`_q_unlink`, `_q_main = None`); (b) then, in the order
      of `state.ids`, each unlinked instance whose current `name` is free in its collection
      (`name not in collection`) is linked with `data.q_collection_for(instance)._q_link(instance)`; the
      others stay pending.
   5. **State**: recursively (dict, list, tuple, set), replaces each `IDIndex(n)` with
      `state.ids[n].instance`; for each `IDState`, `instance._q_state_set(st)` (restores in place,
      including the exact name via the `"name"` key, without callbacks, handlers or msgbus, §2.1.5(3); the ID
      may be unlinked at this moment **[I]**); then links the pending ones, in the order of
      `state.ids` (the final names are unique, hence free); finally `instance.q_tag(*DIRTY_CHANNELS)`
      on each instance in the state.
   6. **Windows and extras**: `quartz.session._q_point_windows(data)` (windows with a tombstoned scene or
      `None` → 1st scene; view layer, screen and workspace fixed if invalid, §2.6.1 rule 3);
      `data.use_autopack` ← `extra["use_autopack"]` if present (unknown keys in `extra` are
      ignored).
5. **`encode(state)`** → `(doc, arrays)`; `doc = {"state_version": STATE_VERSION, "ids": [{"type":
   rna_type, "id_type", "name", "schema", "state": enc(state)} …], "extra": enc(extra)}`, `ids` in
   the order of `state.ids`. `enc` (§2.1.5(5)), in test order: `None`/`bool`/`int`/`str` unchanged
   (`bool` before `int`); finite `float` unchanged, non-finite → `{"__float__": "nan"|"inf"|"-inf"}`;
   `np.generic` → `.item()` and `enc` again; `IDIndex` → `{"__id__": index}`; ID instance
   (`getattr(type(v), "_q_is_id", False)`) present in `state.ids` (by identity) →
   `{"__id__": index}`; ID outside the state (UI, embedded or tombstone) → `FileFormatError` `"outside the
   saved state"`; `list` → list; `tuple` → `{"__tuple__": [...]}`; `set`/`frozenset` →
   `{"__set__": [...]}` with the items encoded and ordered by `sorted` (on `TypeError`, by
   `repr` of the original item); `dict` → `str` keys required (any other → `FileFormatError`
   `"non-string key"`), key of the form `"__…__"` → `FileFormatError` `"reserved key"`, values
   encoded visiting the keys in sorted order; `np.ndarray` → `{"__array__": k}` with `k =
   f"a{n}"`, `n` = counter of the visiting order (deterministic), and `arrays[k] = v` (no copy);
   any other type → `FileFormatError(f"cannot encode value of type {type(v).__name__}")`.
6. **`decode(doc, arrays)`**: structure validated field by field (`doc` `dict`; `state_version`
   `int` ≥ 1, greater than `STATE_VERSION` → `"newer state version"`; `ids` list of `dict` with `type`,
   `id_type`, `name` `str`, `schema` `int` ≥ 1, `state` `dict`; `extra` `dict`), any violation →
   `FileFormatError` `"invalid .qz data"` + field path (e.g. `"ids[3].schema"`). Inverts
   `enc`: a `dict` with any `"__…__"` key MUST have exactly that key and it MUST be one of the
   five markers (otherwise `"unknown marker"`); `{"__id__": n}` (`n` `int`, not `bool`) →
   `IDIndex(n)`; `{"__array__": k}` → `arrays[k]` (missing → `"missing array"`); `__tuple__` →
   `tuple`; `__set__` → `set`; `__float__` → `float("nan"/"inf"/"-inf")` (other text → `"invalid
   .qz data"`). Returns `IDState` with `instance=None`.
7. Round trip: `decode(*encode(s))` reproduces `s` (with `IDIndex` in place of the instances and `set` in
   place of `frozenset`); arrays with the same `dtype` and shape; `float32` comes back bit for bit.

Errors: `FileFormatError` `"unknown ID type"`, `"newer schema"`, `"duplicate ID name"`, `"invalid ID
reference"`, `"outside the saved state"`, `"non-string key"`, `"reserved key"`, `"cannot encode value
of type"`, `"newer state version"`, `"invalid .qz data"`, `"unknown marker"`, `"missing array"`.

#### 2.6.7 `quartz/io/qzfile.py`

```python
MANIFEST_NAME: str = "manifest.json"; DATA_NAME: str = "data.json"; ARRAYS_DIR: str = "arrays/"
def write_container(filepath: str | os.PathLike, manifest: Mapping[str, object], data: Mapping[str, object],
                    arrays: Mapping[str, np.ndarray]) -> None
def read_container(filepath: str | os.PathLike) -> tuple[dict, dict, dict[str, np.ndarray]]
```

1. **Deterministic writing** (§2.1.5(6)): zip; entries in this order: `manifest.json`,
   `data.json`, then `arrays/<k>.npy` with `k` sorted; each entry is a `ZipInfo(name,
   date_time=(1980, 1, 1, 0, 0, 0))` with `compress_type = ZIP_DEFLATED`, `create_system = 3` and
   `external_attr = 0o100644 << 16` (the same on any OS); JSON with `json.dumps(obj,
   ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))` in UTF-8; arrays via
   `np.save(buf, a, allow_pickle=False)`. The same entries produce identical bytes.
2. Writes to a temporary file `<file>.tmp` in the same directory and swaps it in with `os.replace`; on any
   failure the temporary file is deleted and the existing file is left intact. `k` outside `[A-Za-z0-9_.-]+` →
   `FileFormatError` `"invalid array key"`; array with object `dtype` or `np.save` failure →
   `FileFormatError` `"cannot store array"`; JSON serialization failure or `OSError` →
   `FileFormatError` `"cannot write"` with `__cause__`. Validations happen before creating the
   temporary file.
3. **Reading**: any problem → `FileFormatError` with `__cause__`: unreadable file (`"cannot
   read"`), not a zip (`"not a .qz container"`), required entry missing (`"missing entry"`), invalid JSON
   or a top level that is not an object (`"invalid JSON"`), invalid `.npy` or one that would require pickle
   (`np.load(..., allow_pickle=False)`, `"invalid array"`). Unknown entries (including nested
   `arrays/`) are ignored. Returns `arrays` keyed by `k` (without prefix and extension).
4. No format validation (that belongs to §2.6.5).

Errors: `FileFormatError` `"invalid array key"`, `"cannot store array"`, `"cannot write"`, `"cannot
read"`, `"not a .qz container"`, `"missing entry"`, `"invalid JSON"`, `"invalid array"`.

#### 2.6.8 `quartz/testing.py`

```python
@contextmanager
def isolated(*, template: str = "default") -> Iterator["Session"]
def invoke_operator(idname: str, *, event: "Event | None" = None, **props: object) -> set[str]
def drive_modal(idname: str, events: Sequence["Event"], **props: object) -> set[str]
def rna_schema_diff(cls: type, dump_props: Mapping[str, Mapping[str, object]], *, require_all: bool = False,
                    divergences: Mapping[str, str] | None = None) -> list[str]
def function_signature_diff(func: Callable, dump_func: Mapping[str, object], *,
                            divergences: Mapping[str, str] | None = None) -> list[str]
```

1. **`isolated(template)`** (used by the `qz`/`qz_empty` fixtures, §1.1.2). Entry: snapshots of
   `hooks`, `settings`, `handlers`, `timers`, `msgbus` and `loc = translations.locale`
   (`quartz.app.translations`) **before** touching the session; `s =
   session.current()`; `snap = registry.snapshot()` (already with the built-ins); `prov =
   contexts._q_providers_snapshot()`; current depth of the `restrict_blend` stack;
   `s.preferences.q_reset()`; `s.reset(template=template)`; `yield s`. Exit (always, in `finally`;
   an exception from the body propagates afterwards): `registry.restore(snap)`, `contexts._q_providers_restore(prov)`,
   `msgbus.restore`, `timers.restore`, `handlers.restore`, `settings.restore`, `hooks.restore` (reverse
   order); `translations.set_locale(loc)` (writing `PreferencesView.language` calls `set_locale`,
   §2.5.4, and `preferences.q_reset` does not touch `translations`); `restrict_blend` stack truncated to the entry depth; `s.undo.clear()`;
   `s.preferences.q_reset()`; `s.context._q_clear_overrides()`; adapters back to the default:
   `quartz.math.bvhtree.set_object_adapter(None)`, `set_bmesh_adapter(None)`,
   `quartz.types.mesh.set_editmode_hooks()` (if the module exists, §3.0.2);
   `quartz.path.set_blend_filepath_provider(None)`; `quartz.types.set_name_resolver(None)`.
   Nestable with respect to global state (the inner one restores what the outer one had); the session **data**
   is not restored (the inner reset replaces the outer one's scene). `registry.restore` does not
   call the user's `register()/unregister()`.
2. **`invoke_operator(idname, event=None, **props)`** = `quartz.ops._q_call(idname, exec_context=
   "INVOKE_DEFAULT", props=props, force_invoke=True, event=event)[0]`: same poll, same
   messages, same reports and post-processing as §2.6.3, but `invoke` is called if the class has it
   (without depending on `settings.invoke_in_background`).
3. **`drive_modal(idname, events, **props)`**: `ret, op = _q_call(idname, exec_context=
   "INVOKE_DEFAULT", props=props, force_invoke=True, post=False)`; `n = len(op._q_reports)`;
   `RUNNING_MODAL ∉ ret` → `_q_post(type(op), op, ret, undo=None)` and returns `ret`. Otherwise the class
   MUST have `modal` (the "has X" rule of §2.6.3; otherwise `OperatorFailedError` `"modal() is not
   defined"`); `ctx = session.current().context`; for each event: `r = op.modal(ctx, ev)` (exception
   → `OperatorFailedError` `"Error: Python: "` as in step 6), `r = _q_check_return(r)`, `n =
   _q_emit_reports(op, n)`; `"FINISHED" in r` or `"CANCELLED" in r` → `_q_post(...)` with `r` and
   returns `r`; any other result → next event. Events exhausted → returns
   `{"RUNNING_MODAL"}` without calling `cancel` **[I]**. On finishing (any path, including
   an exception), removes `op` from `wm.q_modal_handlers` if it is there.
4. **`rna_schema_diff`** implements §2.4.2 literally: declared = `PropertyDef` values of
   `cls.__dict__` itself, in `__dict__` order; the `q_` prefix needs no entry in the dump; fields and
   `flags` restricted as in §2.4.2 (`flags` compared as a set and shown as a sorted list
   in the message); floats via `to_float32` on both sides and `math.isclose(rel_tol=1e-6)` (two zeros
   are equal); integers and floats compared numerically (`bool` only with `bool`); lists element by
   element (different sizes = difference in the field); `set`/`frozenset` on one side → comparison
   as a set; field on one side only = difference, except `unit` absent ≡ `"NONE"`; exact messages
   from §2.4.2, sorted; omission via `divergences`.
5. **`function_signature_diff`** implements §2.4.3: expected `E` = names in `params` without `output`,
   in order; obtained `G` = `inspect.signature(func)` without `self`/`cls` and without `*args`/
   `**kwargs` parameters (which do not satisfy any expected one). Problems: each name in `E` missing from `G` →
   `"missing parameter '{p}'"`; each name in `G` missing from `E` that is not keyword-only
   with a default positioned after all the names in `E` → `"unexpected parameter '{p}'"`; the
   relative order of the common names differs → `"parameter order differs"` (once); for each common name,
   `"required": True` with a default → `"parameter '{p}' should be required"` and not required without
   a default → `"parameter '{p}' should have a default"`. Each one prefixed with
   `f"{func.__qualname__}: "`; sorted list; omission via `divergences`.

These two helpers depend only on L1 and are testable without any kind of L2.

Errors: `OperatorFailedError` `"modal() is not defined"` (and those of §2.6.3, which propagate).

#### 2.6.9 Tests

All in `tests/unit/runtime/`, with the `qz`/`qz_empty` fixtures (§1.1.2) whenever they touch the
session; tests marked "(isolated)" use neither a session nor L2 types and pass before the siblings
exist; the others pass at the L2 gate (§0.6). Test operators and types are local to the test,
registered inside the fixture (`isolated` undoes the registration). No one compares `len(wm.operators)`
between tests (the list is not cleared on reset).

- `test_session.py`: stable identity of `data`/`wm`/`preferences`/`context`/`undo` across
  `reset` and template switching; `quartz.data is current().data`; `peek() is current()`;
  `Session()` → `RuntimeError` `"use quartz.session.current()"`; `reset(template="x")` →
  `ValueError` `"unknown template"`; order of the reset dispatches (`load_pre("")`,
  `load_factory_startup_post("")`, `load_post("")`) with a `@persistent` handler, and a non-persistent
  `load_post` handler removed and not called; non-persistent timers and msgbus cleared;
  `data.is_dirty is False`, `data.filepath == ""` **[O]**, `data.use_autopack is False`;
  `undo.enabled is False`; context overrides emptied; `wm.q_new_window(scene)` + `reset` →
  `len(wm.windows) == 1` and `wm.windows[0]` is the same object as before; `install_hooks()` idempotent
  (`hooks.snapshot()` equal — same objects — after two calls) and does not touch
  `note_missing`/`repr_root`; `restrict_blend` does not change `session.context`. In a subprocess
  `[sys.executable, "-I", "-c", ...]` with the root inserted in `sys.path` (isolated): importing
  `quartz.session`, `contexts`, `ops`, `undo`, `io`, `io.state`, `io.qzfile`, `testing` leaves
  `hooks.snapshot()` equal to a `hooks.snapshot()` taken right after `hooks.reset()` and
  `quartz.session.peek() is None`; in another identical subprocess (gate), a `@persistent` `load_post` handler attached before the 1st `current()` calls `current()` again and gets the same session
  (reentrancy), and `current()` finishes without recursion.
- `test_factory_scene.py`: each fact in the §2.6.1 table against the `blender_facts` fixture
  (`factory`, tolerance `abs=1e-5`) and the `factory_scene` dump: names, order of `scene.objects` and
  `view_layer.objects` = `Cube, Light, Camera` **[O]**, `data.objects` = `Camera, Cube, Light`,
  `data.materials` = `Dots Stroke, Material` **[O]**; `frame_start/end/current` = `[1, 250, 1]`,
  engine and unit system **[O]**; vertices, faces and edges exact (in the judge's order),
  `uv_first4` **[O]** and the 24 UVs from the table, `sharp_face` all true; `users`: mesh 1,
  `Material` 1, `Dots Stroke` 0, scene 1, Camera object 1 **[O]**; `Dots Stroke.is_grease_pencil`;
  camera (lens, sensor, clip `[0.10000000149011612, 100.0]`), light (1000, radius
  `0.10000000149011612`), World, render, `selected == ["Cube"]`, active `Cube`, `len(wm.windows) ==
  1`, window pointing to scene/view layer/`Layout`, names `WinMan`/`Layout`/`ViewLayer`; template
  `empty` (`qz_empty`): no objects, `world is None`, `camera is None`, view layer and master collection
  present, `context.collection is scene.collection`.
- `test_context.py`: §2.4.4 — `set(CONTEXT_MEMBERS)` == members of the dump (71) and `CONTEXT_METHODS`
  == the 4 methods; `NONE_MEMBERS` == members of the dump without a provider (42) and `providers()` covers the 71;
  factory values from `probes.context_semantics` and the dump's `context` key (non-null/null,
  names, counts) **[O]**; `temp_override(active_object=cam, object=cam, selected_objects=[cam])`
  inside/outside **[O]**, nested, restored after an exception; `_q_clear_overrides()` inside a
  `temp_override` → exiting the `with` does not raise and the stack is left empty; `quartz.types.Context is
  quartz.contexts.Context`; unknown key accepted and invisible
  **[O]**; `context.scene = x` → `ReadOnlyError` `'from "Context" is read-only'` **[O]**; `copy()`
  with the 71 keys in alphabetical order, without methods and with overrides; `path_resolve
  ("scene.frame_current") == 1` **[O]** and a bad path (`"nope"`, `"scene.nope"`, `"copy"`) →
  `ValueError` `"could not be resolved"`; `mode`/`edit_object`/`objects_in_mode` after
  `Object.q_set_mode("EDIT")` on the Cube (`"EDIT_MESH"`, `Cube`, `[Cube]`) **[O]**;
  `asset_library_reference is None` noting `"bpy.context.asset_library_reference"` (`note_missing`
  hook swapped between `hooks.snapshot()` and `restore()`); `register_provider`/
  `unregister_provider` (native disappears; default member goes back to the default; absent → `KeyError`; invalid name
  → `ValueError`) and restoration of the providers by `isolated`; `evaluated_depsgraph_get()`:
  a 1st call settles, the 2nd without change does not dispatch `depsgraph_update_post`, and after
  `ob.location.x = 1` it dispatches with `(scene, depsgraph)`. Isolated part: `Context(SimpleNamespace(
  data=…, wm=SimpleNamespace(windows=[]), preferences=…))` with safe providers returning `None` (`window`,
  `scene`, `active_object` `None`, `selected_objects == []`, `mode == "OBJECT"`), override stack,
  read-only, `copy`, `register_provider`.
- `test_restrict.py`: inside `restrict_blend()` `quartz.data`/`quartz.context` are the restricted ones
  (same identity on each access), `quartz.context.window_manager is s.wm`, `.preferences`,
  `quartz.context.scene` and `quartz.data.objects` → `RestrictedAccessError` (also
  `AttributeError`) with `"has no attribute"`; writing → `RestrictedAccessError`; `session.context` and
  `hooks.current_context()` remain real; `ops.call` works inside; `enabled=None` follows
  `settings.restrict_register` (with `False` it does not restrict); nested `enabled=False` suspends;
  leaving via an exception pops the stack.
- `test_ops_call.py`: local operators registered in the test reproducing `probes.operator_basic` and
  `probes.operator_poll_false_and_returns` **[O]**: returns of `call()`, `call("EXEC_DEFAULT")`,
  `call("INVOKE_DEFAULT")` (runs `execute`), `call("EXEC_DEFAULT", False)`; unknown kwarg, bad enum
  and bad type with the fragments; out-of-range clamped; values do not persist; positional `dict`,
  two `str` and three positionals → `ExecContextError`; invalid context →
  `PropertyTypeError` `"expected a string enum in ("`; poll-before-kwargs order (call log:
  poll once per call, no `execute` when the kwarg is bad); false poll with and without
  `poll_message_set`; return `{"DONE"}`, `None`, `"FINISHED"` (str), exception (`"Error: Python: "`
  + traceback, `__cause__`), `ERROR` report + `CANCELLED` (`"Error: probe error report"`),
  `INFO` printed to `stdout` as `"Info: ..."`; missing operator → `OperatorNotFoundError` with
  `"quartz.ops."` (and the note `"bpy.ops.<id>"`); `settings.api_prefix = "bpy"` changes the message;
  `invoke_in_background=True` calls `invoke` with `Event`; registered local subclass of `Macro` →
  `NotImplementedInQuartz`; `OpCallable.idname()` without registration, `idname_py`, `get_rna_type`,
  `bl_options` (with and without the attribute), `poll()`; `quartz.ops.poll` with an invalid context;
  identity of `quartz.ops.mesh`; `quartz.ops._x` and `quartz.ops.__path__` → `AttributeError`;
  `dir()` of the submodule and of the module; `REGISTER` → the last item of `wm.operators` is the `op`; `UNDO`
  pushes only with undo on and a positional `undo` not false.
- `test_undo.py`: off at the start **[O]**; `push` turns it on; create object + `push` + `undo` → object
  becomes a tombstone and `redo` revives it with the **same** identity; remove mesh (cascade) + `undo` revives
  the mesh and the objects linked again; create a second scene + `push`, remove it (`scenes.remove`) +
  `push` + `undo` → the scene comes back with the same identity and `scene.collection.objects` is accessible
  (master revived, no `RemovedStructError`); `redo` tombstones the scene and the master; rename two IDs swapping the names + `undo`; change `light.type`
  + `undo` brings the class back; prop values and geometry restored; `undo_pre/undo_post`/
  `redo_pre/redo_post` with the scene; no step → `False` and nothing dispatched; limit
  `settings.undo_steps` (via `monkeypatch`/`settings`); `history`/`index`/`jump`; WM, screens and
  workspaces outside the state (identity and window intact); `clear()` and `Session.reset` turn it off.
- `test_state.py`: (isolated) `encode`/`decode` with hand-built `IDState` and a local fake class
  `@builtin_struct` with `_q_is_id = True` (without registering an ID type): each marker of §2.1.5(5),
  `float32` bit for bit, `nan`/`inf`, `tuple`/`set`, non-`str` key and reserved key →
  `FileFormatError`, unsupported value, reference outside the state, array names `a0, a1, …` in
  visiting order, `decode` of a malformed document (`"invalid .qz data"`), missing array, unknown
  marker, dict with a marker and another key, greater `state_version`. In the session: `capture` (order
  of `q_iter_ids`, no UI, independent deep copy), `apply` in place (identity, tombstones
  reverted, extra IDs removed without cascade, names swapped between two IDs), `apply` of a decoded
  state creates new IDs via `_q_construct` with resolved references, `PointLight` recreated
  as `PointLight`, chained `q_upgrade` (via `monkeypatch` of `q_schema_version = 3` and
  `q_upgrade` on a built-in class, e.g. `Camera`; called with `v = 1` and `v = 2`), newer schema
  → `"newer schema"` without changing `data`, `q_dirty` stamped on all channels after `apply`.
- `test_qzfile.py`: (isolated) round trip of `write_container`/`read_container` with arrays of several
  `dtype`/shapes (`float32`, `int32`, `bool_`, 2D); two equal `write`s → identical bytes; order of the
  entries; fixed `date_time`; zip without `manifest.json`, non-zip file, invalid JSON, object `.npy`
  (zip assembled by hand with `zipfile`) → `FileFormatError` with the fragments; object array on
  write → `"cannot store array"` without destroying the existing file or leaving a `.tmp`; writing only to
  `tmp_path`.
- `test_io_qz.py`: `save_qz` → `load_qz` of the factory reproduces names, counts, transforms,
  geometry, UVs, materials, `users`, selection and active; `data.filepath`/`is_saved`/`is_dirty` after
  saving, after `copy=True` and after loading; `read_manifest` (exact keys of §2.1.5(6), `"author":
  "D1on1n"`); `save_pre/save_post`, `load_pre/load_post` with the absolute path, `save_post_fail`
  and `load_post_fail` on failure; non-persistent handler removed on load; corrupted file →
  `FileFormatError` and session intact; wrong format (`"not a Quartz .qz file"`), newer version
  (`"newer format version"`), invalid manifest; `.blend` → `"'.blend' files are not supported"`
  without dispatch; WM/window keep identity and point to the 1st scene; `undo` cleared.
- `test_testing.py`: `isolated` restores hooks, settings, handlers, timers, msgbus, providers and
  registry (class registered inside disappears outside; handler attached inside disappears outside),
  `translations.locale` (`translations.set_locale("pt_BR")` inside → `"en_US"` outside, also when
  the body raises), returns
  adapters and extension points to the default and propagates the body's exception; `invoke_operator` calls
  `invoke` with the given `Event`; `drive_modal` with a local modal operator (events until `FINISHED`, until
  `CANCELLED`, exhausted → `{"RUNNING_MODAL"}`, no `modal` → `"modal() is not defined"`, invalid
  return from `modal` → `"incompatible return value"`, removed from `wm.q_modal_handlers`).
  (isolated) `rna_schema_diff`/`function_signature_diff` over fake classes and dumps: each message
  of §2.4.2 and §2.4.3, `q_` rule, `require_all`, `float32` tolerance, absent `unit`, `divergences`
  by field/prop/qualname/parameter, output sorted and empty when conforming.
- `test_native_flow.py` (gate §2.0.5(5)): without `quartz.compat` (the `sys.modules` keys that
  start with `bpy` or `quartz.compat` are the same before and after, and `settings.api_prefix ==
  "quartz"`), under `registry.owner_scope("qz_native_flow")`: a `PropertyGroup`, an `Operator`
  (`qz_native.flow`, changes a prop of the group and returns `{"FINISHED"}`) and a `Panel` registered with
  `quartz.utils.register_class`; `Scene.qz_native = PointerProperty(type=PG)`;
  `quartz.ops.qz_native.flow(value=3)` → `{"FINISHED"}` and the value stored in
  `quartz.context.scene.qz_native`; `quartz.ui.draw_ui(Panel)` → `DrawResult.ok`; `del
  Scene.qz_native` and `unregister_class` in reverse order; at the end `classes_owned_by("qz_native_flow")
  == []`, `type_props_owned_by(...) == []`, `quartz.ops.qz_native.flow()` → `OperatorNotFoundError`
  and, for the RNA name, `quartz.types.resolve_name("QZ_NATIVE_OT_flow") is None`,
  `quartz.registry.lookup("QZ_NATIVE_OT_flow") is None` and `not hasattr(quartz.types,
  "QZ_NATIVE_OT_flow")`.

### 2.7 Built-in operators (`l2-operators`)

The built-in operators are ordinary `Operator` classes (§2.5.2), registered through the public API
(`quartz.registry.register_class`, §2.5.1) under the owner `"quartz.builtin"` and called by
`quartz.ops.call` (§2.1.8, §2.6.3) exactly like those of an add-on (D12). This task consumes from L1
only names from §0/§1 and from L2 only the names that the owning sections publish: `Operator`,
`poll_message_set`, `report`, `is_property_set` (§2.5.2, §1.6.7), `quartz.registry` (§2.5.1),
`Object`, `object_modes_for`, `OBJECT_MODES`, `Object.q_set_mode` (§2.2.6), `CollectionObjects`
(§2.2.7), `Scene`, `ViewLayer`, `LayerObjects`, `ToolSettings`, `View3DCursor` (§2.2.8), `ID.copy`,
`ID.users`, `ID.q_tag` (§2.2.4, §2.2.3), `IDCollection.new/remove` (§2.2.5), `Mesh` and the editing
protocol (§2.3.1, §2.1.9), `BlendDataCameras`/`BlendDataLights` (§2.3.3, §2.3.4), `Menu` (§2.5.3),
`quartz.ui.draw_menu` (§2.5.6), `WindowManager.q_ui_requests` (§2.2.10), `quartz.session.current/
reset` and `Session.undo/data` (§2.6.1), the context members of §2.6.2, `UndoStack` (§2.6.4) and
`quartz.io.save_qz/load_qz` (§2.6.5).

Built-in operators (43; each one declares **all** the props of the `ops.submodules` dump, §2.4.4):

| Module | `bl_idname` |
|---|---|
| `object.py` (18) | `object.mode_set`, `object.editmode_toggle`, `object.select_all`, `object.select_by_type`, `object.delete`, `object.duplicate`, `object.transform_apply`, `object.shade_smooth`, `object.shade_flat`, `object.add`, `object.empty_add`, `object.camera_add`, `object.light_add`, `object.parent_set`, `object.parent_clear`, `object.location_clear`, `object.rotation_clear`, `object.scale_clear` |
| `mesh.py` (11) | `mesh.primitive_plane_add`, `mesh.primitive_cube_add`, `mesh.primitive_circle_add`, `mesh.primitive_uv_sphere_add`, `mesh.primitive_ico_sphere_add`, `mesh.primitive_cylinder_add`, `mesh.primitive_cone_add`, `mesh.primitive_grid_add`, `mesh.primitive_torus_add`, `mesh.primitive_monkey_add`, `mesh.select_all` |
| `transform.py` (3) | `transform.translate`, `transform.rotate`, `transform.resize` |
| `ed.py` (4) | `ed.undo`, `ed.redo`, `ed.undo_push`, `ed.undo_history` |
| `wm.py` (7) | `wm.read_factory_settings`, `wm.read_homefile`, `wm.save_as_mainfile`, `wm.save_mainfile`, `wm.open_mainfile`, `wm.call_menu`, `wm.call_menu_pie` |

Rules common to all 43 built-ins:

1. **Class**: direct subclass of `quartz.types.operator.Operator`; Python name = RNA name
   (`OBJECT_OT_select_all`); `bl_idname` from the table above; `bl_label` and `bl_description` with
   original wording in English (non-empty); `bl_options` = exactly the set from the dump
   `ops.submodules[mod][op]["bl_options"]` **[O]** (e.g. `object.mode_set` → `set()`,
   `transform.translate` → `{"BLOCKING", "REGISTER", "UNDO"}`, `ed.undo_push` → `{"INTERNAL"}`).
2. **Properties**: each built-in declares, by annotation with the factories of `quartz.props`, **all**
   the props that the dump lists for it, with the names from the dump and no others (§2.4.4). For the
   operators in `ops.detail_ops` (all of `object.*`, `mesh.primitive_*` and `transform.*` in this
   section) the fields (`type`, `subtype`, `unit`, size, `default`, limits, `step`, `precision`,
   `items`, `maxlen`, flags `HIDDEN`/`SKIP_SAVE`/`ENUM_FLAG`) MUST be those of the dump **[O]**, except for the
   divergences listed in §2.7.8 (`test_operator_schema.py`). For the others (`mesh.select_all`,
   `ed.*`, `wm.*`) the dump only provides `type` **[O]**: the type MUST match and the other fields are those
   of this section **[I]**. The declaration order MAY differ from that of the dump (the tests do not check it); the
   dump's order is recommended.
3. **Enum items**: a static `EnumProperty` receives `items` as a sequence of triples
   `(identifier, name, "")` (name with original wording in English), in the dump's order — never
   bare strings, which `normalize_enum_items` (§1.6.4) does not accept. The tuple constants of
   identifiers in this section (`ALIGN_ITEMS`, `ORIENT_TYPES`, …) are converted into these triples
   at declaration.
4. **Methods**: each built-in defines `execute(self, context) -> set[str]` and, where indicated,
   `poll(cls, context) -> bool` (classmethod); none defines `invoke`, `modal`, `draw`, `cancel` or
   `check` (with `INVOKE_DEFAULT`, `quartz.ops` falls back to `execute`, §2.1.8(6)).
5. **Context**: all scene data comes from members of `context` (`scene`, `view_layer`,
   `active_object`, `selected_objects`, `selected_editable_objects`, `selectable_objects`,
   `collection`, `mode`, `objects_in_mode`, `objects_in_mode_unique_data`, `blend_data`,
   `window_manager`, §2.6.2), so that `context.temp_override(...)` holds **[O]**; selection and active
   are written to the context's view layer (`ob.select_set(state, view_layer=context.view_layer)`,
   `context.view_layer.objects.active = ob`).
6. **No nested calls**: a built-in MUST NOT call `quartz.ops` (reuse is through functions of
   `common.py` and of each module), so as not to stack undo or reports twice; MUST NOT call
   `UndoStack.push` (only `ed.undo_push` does; the undo step of the others is pushed by
   `quartz.ops`, §2.1.8(9)); MUST NOT dispatch handlers (that is up to `Scene`, `Depsgraph`,
   `UndoStack`, `Session.reset` and `quartz.io`, §2.1.2).
7. **Predictable failures** (object type, `.blend` path, parenting cycle…) become
   `self.report({"ERROR"}, message)` + `{"CANCELLED"}`, which `quartz.ops.call` converts into
   `OperatorFailedError("Error: " + message)` **[O]** (mechanism of §2.1.8(8)). The built-in
   checks everything **before** changing data, including before leaving edit mode: when it
   cancels, nothing has changed.
8. **"Object-mode poll"** = `context.mode == "OBJECT"` **[I]**; when it fails without
   `poll_message_set`, the message is the default `"failed, context is incorrect"` (§2.1.8(4)).
9. **Computations**: intermediate matrices and vectors in `float64` (`quartz.math`); only the final write to
   props/geometry rounds to `float32` (§0.2). Iteration is always in the order of the context members (view layer
   order) and, among objects, in the order of the received list — deterministic result.
10. **Layers and imports**: `quartz/operators/**` imports only L1 and L2 (never L3, not even inside
    functions). At module level, `object.py`, `mesh.py`, `transform.py`, `ed.py` and `wm.py` import
    only stdlib, `quartz.errors`, `quartz.props`, `quartz.rna`, `quartz.math`, `quartz.geometry`,
    `quartz.types.operator` (base `Operator`) and `quartz.operators.common`; every other L2 name
    (`quartz.session`, `quartz.io`, `quartz.registry`, `quartz.ui`, `quartz.types.ui`, ID
    types) is imported inside the functions. No module of the package has import side effects (defining
    subclasses of `Operator` registers nothing).

#### 2.7.1 `quartz/operators/__init__.py`

```python
BUILTIN_OWNER: str = "quartz.builtin"
BUILTIN_MODULES: tuple[str, ...] = ("quartz.operators.object", "quartz.operators.mesh",
                                    "quartz.operators.transform", "quartz.operators.ed",
                                    "quartz.operators.wm")
def builtin_classes() -> tuple[type, ...]
    # imports BUILTIN_MODULES in order (lazy, cached) and concatenates the CLASSES of each: 18 + 11 + 3 + 4 + 7 = 43
def register_builtin() -> None
    # idempotent; with registry.owner_scope(BUILTIN_OWNER): registry.register_class(c) for each unregistered c
def unregister_builtin() -> None
    # in reverse order: registry.unregister_class(c) for each registered c; idempotent
def is_builtin(cls_or_idname: type | str) -> bool
    # class: is in builtin_classes() (identity); str: idname_py ("object.select_all") or RNA name
    # ("OBJECT_OT_select_all") of some built-in class (registered or not); other type -> False
```

1. At module level the package imports only the stdlib; `quartz.registry` and the operator modules are
   imported inside the functions. `register_builtin()` MUST NOT touch `quartz.session` (it is called
   by `quartz.session.current()` during session creation, §2.1.7, §2.6.1).
2. `builtin_classes()` always returns the same tuple (same identity of the classes), in the order of the
   table in the introduction of this section (module by module; within each module, the order of its
   `CLASSES`, which follows the table).
3. `register_builtin()` uses `registry.is_registered(c)` to skip those already registered; if a user class
   occupies the same RNA name, the silent replacement of §2.1.6(4) applies **[O]**. Each registered class
   has `registry.owner_of(c) == BUILTIN_OWNER`; `registry.counts_by_base()` does not count them
   (it ignores owners that start with `"quartz."`, §2.5.1).
4. `unregister_builtin()` followed by `register_builtin()` reproduces the same state (same classes,
   props and `bl_options`; property classes recreated by the registration, §2.5.2).
   `registry.restore(snapshot)` from `quartz.testing.isolated` is the normal cleanup path in
   tests (§2.6.8); these functions keep no state of their own beyond the `builtin_classes` cache.

No errors of their own (a registration failure propagates the error of §2.1.6, which indicates a declaration bug).

#### 2.7.2 `quartz/operators/common.py`

```python
# ---- public names consumed by other tasks (l3-compat-math-extras, §3.2) ----
def deselect_all(view_layer: "ViewLayer") -> None
def add_matrix(context: "Context", *, location: Sequence[float] | None = None,
               rotation: "Sequence[float] | Euler | Quaternion | Matrix | None" = None,
               scale: Sequence[float] | None = None, align: str = "WORLD") -> Matrix
def object_data_add(context: "Context", obdata: "ID | None", *, name: str | None = None,
                    matrix: Matrix | None = None) -> "Object"
# ---- names of this task ----
ALIGN_ITEMS: tuple[str, ...] = ("WORLD", "VIEW", "CURSOR")                     # [O] dump
def operator_add_matrix(op: "Operator", context: "Context") -> Matrix
    # add_matrix with location/rotation/scale of the operator ONLY if op.is_property_set(name) (otherwise None) and align = op.align
def is_object_mode(context: "Context") -> bool                                # context.mode == "OBJECT"
def ensure_object_mode(context: "Context") -> None                           # objects_in_mode -> q_set_mode("OBJECT")
def top_level_objects(objects: Iterable["Object"]) -> list["Object"]         # removes those with an ancestor in the list; keeps the order
def scene_collections_of(ob: "Object", scene: "Scene") -> list["Collection"]  # collections of the scene tree that contain ob
def edit_meshes(context: "Context") -> list[tuple["Object", "Mesh"]]         # meshes in edit mode ready for direct writing
# kit of shared props (each call returns a NEW _PropertyDeferred; dump fields [O]):
def align_prop(*, hidden: bool = False) -> _PropertyDeferred
    # EnumProperty(items=[(i, name, "") for i in ALIGN_ITEMS], default="WORLD"); hidden -> options={"HIDDEN"} (camera_add)
def location_prop() -> _PropertyDeferred
    # FloatVectorProperty(size=3, subtype="XYZ_LENGTH", unit="LENGTH", default=(0.0, 0.0, 0.0), min=-1e12, max=1e12,
    #                     soft_min=-1000.0, soft_max=1000.0, step=1.0, precision=3, options={"SKIP_SAVE"})
def rotation_prop() -> _PropertyDeferred
    # FloatVectorProperty(size=3, subtype="EULER", unit="ROTATION", default=(0.0, 0.0, 0.0), min=-1e12, max=1e12,
    #                     soft_min=-2π, soft_max=2π, step=10.0, precision=3, options={"SKIP_SAVE"})
def scale_prop() -> _PropertyDeferred          # like location_prop, but options={"HIDDEN", "SKIP_SAVE"} (default (0, 0, 0) [O])
def enter_editmode_prop() -> _PropertyDeferred # BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})
def distance_prop(default: float = 1.0, *, soft_min: float = 0.001) -> _PropertyDeferred
    # FloatProperty(subtype="DISTANCE", unit="LENGTH", default=default, min=0.0, max=1e12, soft_min=soft_min,
    #               soft_max=100.0, step=1.0, precision=3)
```

At module level `common.py` imports only stdlib, `quartz.math` and `quartz.props`; L2 names enter
only in annotations (`TYPE_CHECKING`) or inside the functions (so that `add_matrix` is testable with
L1 only, §0.6). `1e12`, `0.001` and `2π` become `999999995904.0`, `0.0010000000474974513` and
`6.2831854820251465` in `to_rna_dict` (float32, §1.6.4), as in the dump **[O]**.

1. `deselect_all(view_layer)`: `ob.select_set(False, view_layer=view_layer)` for each object in
   `view_layer.objects`; the active object does not change.
2. `add_matrix(context, ...)` returns the 4×4 `Matrix` `Matrix.LocRotScale(loc, rot3, scl)`:
   - `align` outside `ALIGN_ITEMS` → `ValueError` with `f'align "{align}" not in ('` (checked
     first);
   - `loc` = `location` if given, otherwise `context.scene.cursor.location` (new objects are born
     at the cursor) **[I]**;
   - `rot3`: a given `rotation` wins over any `align` **[I]** (`Euler`/`Quaternion`/`Matrix` 3×3 or 4×4
     converted to 3×3; a sequence of 3 = Euler `"XYZ"`); otherwise `align == "WORLD"` → identity,
     `"CURSOR"` → 3×3 part of `context.scene.cursor.matrix`, `"VIEW"` → identity (headless, no
     `region_data`) **[I]**;
   - `scl` = `scale` if given, otherwise `(1, 1, 1)`.
3. `operator_add_matrix(op, context)`: for each name in `("location", "rotation", "scale")`, the value
   is `getattr(op, name)` if the class declares the prop **and** `op.is_property_set(name)`, otherwise `None`
   (props absent from the class — the torus has no `scale` — count as not given); `align = op.align`.
   The dump's `scale` has default `(0, 0, 0)` and is hidden: it only applies if the caller passed it **[I]**.
4. `object_data_add(context, obdata, *, name=None, matrix=None)`:
   1. name = `name`, otherwise `obdata.name`, otherwise `"Empty"`; `ob = context.blend_data.objects.new(name,
      obdata)` (unique name with `.NNN`, §2.1.4(5));
   2. `context.collection.objects.link(ob)` (or `context.scene.collection` if `context.collection`
      is `None`; in the `empty` template it is the master collection);
   3. if `ob` is in `context.view_layer.objects`: `deselect_all(view_layer)`, `ob.select_set(True,
      view_layer=view_layer)`, `view_layer.objects.active = ob` **[O]** (the new object becomes active and
      the only one selected); otherwise (excluded collection) selection and active do not change **[I]**;
   4. `matrix` not `None` → `ob.matrix_world = matrix` (immediate decomposition, §2.2.6); returns `ob`.
   Does not change anyone's mode (the caller decides, e.g. `ensure_object_mode`).
5. `ensure_object_mode(context)`: if `context.mode != "OBJECT"`, calls `o.q_set_mode("OBJECT")` on
   each object in `list(context.objects_in_mode)` (leaves edit mode, saving via `flush`, §2.1.9).
6. `top_level_objects(objects)`: materializes the list; keeps, in the received order, each object that has
   no ancestor (`parent`, `parent.parent`, …) in the list (comparison by identity).
7. `scene_collections_of(ob, scene)`: `[scene.collection] + scene.collection.children_recursive`
   filtered by `ob in c.objects`, in that order **[I]**.
8. `edit_meshes(context)`: only with `context.mode == "EDIT_MESH"` (otherwise `[]`); for each object in
   `context.objects_in_mode_unique_data` whose `data` is `Mesh`: `data.q_flush_edit()` (writes the L3 BMesh,
   if any), then `data.q_edit_data = None` (the next `bmesh.from_edit_mesh` rebuilds
   from the geometry) and includes `(object, mesh)` in the received order. Divergence **[I]**: a BMesh
   obtained before the operator call becomes stale. Whoever writes to `mesh.q_geometry` afterwards
   calls `mesh.q_tag_geometry()`; writes through `foreach_set`/props already stamp the channel (§2.3).

Errors: `ValueError` (`'align "'`), only in `add_matrix`.

#### 2.7.3 `quartz/operators/object.py`

```python
CLASSES: tuple[type, ...]                 # the 18 classes below, in this order
LIGHT_OBJECT_NAMES: Mapping[str, str] = {"POINT": "Point", "SUN": "Sun", "SPOT": "Spot", "AREA": "Area"}   # [I]
OBJECT_TYPE_IDS: tuple[str, ...]          # the 16 items of Object.type, literal copied from the dump, in dump order [O]
DUPLICATE_MODE_IDS: tuple[str, ...]       # the 32 items of object.duplicate.mode, literal copied from the dump, in dump order [O]
def set_objects_mode(context: "Context", mode: str, *, toggle: bool = False) -> set[str]
def mode_items(self: object, context: "Context | None") -> list[tuple[str, str, str]]   # dynamic items of mode_set

# "poll OM" = object mode poll (common rule 8); props without comment = dump fields, without flags
class OBJECT_OT_mode_set(Operator):          # "object.mode_set"; bl_options set() [O]; poll: active_object not None [I]
    mode: EnumProperty(items=mode_items, default="OBJECT", options={"SKIP_SAVE"})   # DYNAMIC [O]
    toggle: BoolProperty(default=False, options={"SKIP_SAVE"})
class OBJECT_OT_editmode_toggle(Operator):   # no props; poll: active not None with "EDIT" in object_modes_for(active) [I]
class OBJECT_OT_select_all(Operator):        # poll OM; action: Enum TOGGLE|SELECT|DESELECT|INVERT = "TOGGLE" (HIDDEN, SKIP_SAVE)
class OBJECT_OT_select_by_type(Operator):    # poll OM; extend: Bool False; type: Enum (16 types) = "MESH"
class OBJECT_OT_delete(Operator):            # poll OM; use_global: Bool False; confirm: Bool True (both HIDDEN, SKIP_SAVE)
class OBJECT_OT_duplicate(Operator):         # poll OM; linked: Bool False (SKIP_SAVE); mode: Enum (32 items) = "TRANSLATION" (HIDDEN)
class OBJECT_OT_transform_apply(Operator):   # poll OM; location, rotation, scale, properties, corrective_flip_normals: Bool True;
                                             #          isolate_users: Bool False (HIDDEN, SKIP_SAVE)
class OBJECT_OT_shade_smooth(Operator):      # poll OM; keep_sharp_edges: Bool True
class OBJECT_OT_shade_flat(Operator):        # poll OM; keep_sharp_edges: Bool True
class OBJECT_OT_add(Operator):               # radius: distance_prop(); type: Enum (16) = "EMPTY"; enter_editmode, align, location, rotation, scale: kit
class OBJECT_OT_empty_add(Operator):         # type: Enum PLAIN_AXES…IMAGE (8) = "PLAIN_AXES"; radius: distance_prop(); align; location; rotation; scale
class OBJECT_OT_camera_add(Operator):        # enter_editmode; align: align_prop(hidden=True); location; rotation; scale
class OBJECT_OT_light_add(Operator):         # type: Enum POINT|SUN|SPOT|AREA = "POINT"; radius: distance_prop(); align; location; rotation; scale
class OBJECT_OT_parent_set(Operator):        # poll OM and active not None; type: Enum (13) = "OBJECT"; xmirror: Bool False; keep_transform: Bool False
class OBJECT_OT_parent_clear(Operator):      # poll OM; type: Enum CLEAR|CLEAR_KEEP_TRANSFORM|CLEAR_INVERSE = "CLEAR"
class OBJECT_OT_location_clear(Operator):    # poll OM; clear_delta: Bool False
class OBJECT_OT_rotation_clear(Operator):    # poll OM; clear_delta: Bool False
class OBJECT_OT_scale_clear(Operator):       # poll OM; clear_delta: Bool False
```

The static enums of `select_by_type.type`, `add.type` and `duplicate.mode` are built (common rule
3) from those local literals, defined before the classes: the class body runs at import and
common rule 10 forbids importing `quartz.types.object` at module level. The other static enums
of the block (`empty_add.type`, `parent_set.type`, …) are also local literals copied from the dump.
All classes in `object.py` except `mode_set` have `bl_options == {"REGISTER", "UNDO"}` **[O]**.
"kit" = `enter_editmode_prop()`, `align_prop()`, `location_prop()`, `rotation_prop()`,
`scale_prop()` (§2.7.2), in the dump's order. The four `*_add` have no poll (true at the factory,
**[O]** `ops.poll_in_background`); before creating anything they validate their own arguments and
then call `ensure_object_mode(context)` **[I]**.

1. **`mode_items(self, context)`**: `context` `None` → `quartz.rna.hooks.current_context()`; active
   `a = context.active_object`; no context or `a` `None` → the 14 of `OBJECT_MODES` in the
   dump's order **[I]**; otherwise `object_modes_for(a)` (mesh: `OBJECT, EDIT, SCULPT, VERTEX_PAINT,
   WEIGHT_PAINT, TEXTURE_PAINT` **[O]**). Each item `(id, name, "")` with its own name. `mode="POSE"`
   on a mesh → `PropertyTypeError` `'Converting py args to operator properties: enum "POSE" not
   found in (\'OBJECT\', \'EDIT\', \'SCULPT\', \'VERTEX_PAINT\', \'WEIGHT_PAINT\',
   \'TEXTURE_PAINT\')'` **[O]** (produced by `_q_assign`, §2.5.2; the poll runs before, §2.1.8(4)).
2. **`set_objects_mode(context, mode, *, toggle=False)`** (used by `mode_set` and
   `editmode_toggle`): `a` = active (`None` → `{"CANCELLED"}`); target = `"OBJECT"` if `toggle` and
   `a.mode == mode` **[O]**, otherwise `mode`; target `== a.mode` → `{"FINISHED"}` with no change **[I]**.
   `L = list(context.objects_in_mode)` (empty if `a.mode == "OBJECT"`); if target `!= "OBJECT"`: `E =
   [a] + [o for o in context.selected_objects if o is not a and o.type == a.type and target in
   object_modes_for(o)]` **[I]**. Target `"OBJECT"` → `o.q_set_mode("OBJECT")` for `o` in `L`; otherwise
   `o.q_set_mode("OBJECT")` for `o` in `L` that is not in `E` (identity), then
   `o.q_set_mode(target)` for `o` in `E`. Returns `{"FINISHED"}`. Facts **[O]** (judge `modes`): after
   `mode_set(mode="EDIT")` with `Cube` active, `context.mode == "EDIT_MESH"`, `objects_in_mode ==
   [Cube]`, `cube.data.is_editmode`; `mode_set(mode="OBJECT")` → `"OBJECT"`; `mode_set(mode="EDIT",
   toggle=True)` twice → `"EDIT_MESH"` and then `"OBJECT"`.
3. **`editmode_toggle`** = `set_objects_mode(context, "EDIT", toggle=True)`.
4. **`select_all(action)`** over `S = context.selectable_objects`: `TOGGLE` → if any of `S` is
   selected it becomes `DESELECT`, otherwise `SELECT` **[O]**; `SELECT`/`DESELECT` → `select_set(True/False)`
   on all of `S`; `INVERT` → inverts each one. The active object does not change. `{"FINISHED"}`. Facts **[O]** (judge
   `ops.select_all`, starting from no selected object — probe state after the primitives,
   with the three factory objects): `TOGGLE` → `Camera, Cube, Light`; `TOGGLE` → none; `INVERT` →
   all three.
5. **`select_by_type(extend, type)`**: without `extend`, deselects `S`; selects those in `S` with `o.type
   == type` **[I]**. `{"FINISHED"}`.
6. **`delete(use_global, confirm)`**: `sel = list(context.selected_objects)`; empty →
   `{"CANCELLED"}` **[I]**. For each `ob`: `use_global` → `blend_data.objects.remove(ob)`; otherwise
   `c.objects.unlink(ob)` for `c` in `scene_collections_of(ob, context.scene)` and, if
   `ob.users_collection` became empty, `blend_data.objects.remove(ob)` **[I]**. The `data` is NOT
   removed: the mesh is left orphaned with 0 users (removal rule of §2.1.4(3.5), **[O]** for
   `objects.remove`). `confirm` is ignored (no dialog). Report `{"INFO"}` `f"Deleted {n}
   object(s)"` **[I]**. `{"FINISHED"}`.
7. **`duplicate(linked, mode)`**: `sel = list(context.selected_objects)`; empty → `{"CANCELLED"}`
   **[I]**. For each `ob`, in order: `new = ob.copy()` (name `.NNN`, §2.1.4(6)); if not `linked` and
   `ob.data` is not `None`: `new.data = ob.data.copy()` **[O]**; `new` is linked to each collection in
   `scene_collections_of(ob, context.scene)` **[I]**. Then: a copy whose `parent` was also
   duplicated now points to the parent's copy (keeping `matrix_parent_inverse`) **[I]**;
   originals deselected, copies selected; if the active object was duplicated, the copy becomes active
   **[O]**. `mode` is ignored (no interactive transform). Facts **[O]** (judge `ops.duplicate`,
   `Cube` the only one selected and active): return `{"FINISHED"}`, active `Cube.001` with mesh `Cube.001`,
   selected `[Cube.001]`, `cube.select_get()` false; then `duplicate(linked=True)` creates an
   object whose mesh is `Cube.001` (shared).
8. **`transform_apply(location, rotation, scale, properties, corrective_flip_normals,
   isolate_users)`** over `sel = list(context.selected_editable_objects)`; empty → `{"CANCELLED"}`
   **[I]**. In order:
   1. pre-check (nothing changes if it fails): an object whose `data` is a `Mesh` with `data.users > 1` and
      `isolate_users` false → report `{"ERROR"}` with `"multi user"` and `{"CANCELLED"}` **[I]**;
   2. `isolate_users` and `data.users > 1` → `ob.data = ob.data.copy()` **[I]**;
   3. an object without `Mesh` (empty, camera, light) → report `{"WARNING"}` with `"not supported"` and it is
      skipped **[I]**;
   4. `B_old = ob.matrix_basis.copy()`; zeroes the requested channels (`location → (0,0,0)`; rotation → zero
      in the mode of `rotation_mode`: Euler `(0,0,0)`, `QUATERNION` `(1,0,0,0)`, `AXIS_ANGLE`
      `(0,0,1,0)`; `scale → (1,1,1)`; deltas untouched) **[I]**; `B_new = ob.matrix_basis`; `A =
      B_new.inverted_safe() @ B_old` (so `B_new · A == B_old`);
   5. `ob.data.transform(A)`; `A.determinant() < 0` and `corrective_flip_normals` →
      `ob.data.flip_normals()` **[I]**; each child `c` of `ob.children`: `c.matrix_parent_inverse = A
      @ c.matrix_parent_inverse` (everything's world transform stays unchanged) **[I]**; `properties` is ignored
      for meshes.
   Returns `{"FINISHED"}`.
9. **`shade_smooth(keep_sharp_edges)` / `shade_flat(keep_sharp_edges)`**: distinct meshes (by
   identity, in order of first occurrence) of the `MESH` objects in
   `context.selected_editable_objects`; none → `{"CANCELLED"}` **[I]**. Smooth: stores a copy of the
   array of the `"sharp_edge"` attribute of `mesh.q_geometry.attributes` (if it exists), calls
   `mesh.shade_smooth()` (which removes `sharp_face` and `sharp_edge`, §2.3.1) and, with `keep_sharp_edges`
   and an existing copy, recreates `"sharp_edge"` (`BOOLEAN`, `EDGE`) with the copy and calls
   `mesh.q_tag_geometry()` **[I]**. Flat: `mesh.shade_flat()`; without `keep_sharp_edges`, removes
   `"sharp_edge"` if it exists and calls `mesh.q_tag_geometry()` **[I]**. `{"FINISHED"}`.
10. **`add(radius, type, ...)`**: first validates `type`: `EMPTY` → `data = None`, name `"Empty"`;
    `MESH` → empty mesh `"Mesh"`; `CAMERA` → camera `"Camera"`; `LIGHT` → light `"Light"` of type
    `"POINT"` **[I]**; other types → report `{"ERROR"}` `f'object type "{type}" is not supported
    in Quartz'` and `{"CANCELLED"}` (nothing changed). Then `ensure_object_mode(context)`; creates the data
    (`blend_data.meshes.new("Mesh")`, `cameras.new("Camera")` or `lights.new("Light", "POINT")`);
    `ob = object_data_add(context, data, name=name, matrix=operator_add_matrix(self, context))`;
    `EMPTY` → `ob.empty_display_size = radius`; `enter_editmode` and `"EDIT"` in
    `object_modes_for(ob)` → `ob.q_set_mode("EDIT")` **[I]**. `radius` only affects empties **[I]**.
    `{"FINISHED"}`.
11. **`empty_add`**: like `add` with `EMPTY`, plus `ob.empty_display_type = type` and
    `ob.empty_display_size = radius`. **`camera_add`**: `cameras.new("Camera")`, object
    `"Camera"`; `enter_editmode` has no effect (a camera has no edit mode); `scene.camera` does NOT
    change (no viewport) **[I]**. **`light_add`**: `lights.new(LIGHT_OBJECT_NAMES[type], type)`,
    object with the same name **[I]**; `radius` ignored **[I]**.
12. **`parent_set(type, xmirror, keep_transform)`**: `p = context.active_object`; children `F = [o for
    o in context.selected_editable_objects if o is not p]`; empty `F` → `{"CANCELLED"}` **[I]**;
    `type != "OBJECT"` → `{"ERROR"}` `f'parent type "{type}" is not supported in Quartz'` +
    `{"CANCELLED"}`; any `c` in `F` in the parent chain of `p` (`p.parent`, `p.parent.parent`, …) →
    `{"ERROR"}` with `"Loop in parents"` + `{"CANCELLED"}` **[I]**. For each `c`: `W =
    c.matrix_world.copy()`; `c.parent = p`; `c.parent_type = "OBJECT"`; `c.matrix_parent_inverse =
    p.matrix_world.inverted_safe()` (the child's world transform becomes its basis); `keep_transform` →
    `c.matrix_world = W` **[I]**. `xmirror` ignored. `{"FINISHED"}`.
13. **`parent_clear(type)`** on the objects in `context.selected_editable_objects` that have a `parent`:
    `CLEAR` → `parent = None` and `matrix_parent_inverse` = identity; `CLEAR_KEEP_TRANSFORM` → stores
    `W = matrix_world.copy()`, same, `matrix_world = W`; `CLEAR_INVERSE` → only
    `matrix_parent_inverse` = identity **[I]**. `{"FINISHED"}`.
14. **`location_clear` / `rotation_clear` / `scale_clear(clear_delta)`** on the objects in
    `context.selected_editable_objects`: `location` → `(0,0,0)`; rotation → zero in the mode of
    `rotation_mode` (as in 8.4); `scale` → `(1,1,1)`; a component with `lock_location[i]`/
    `lock_rotation[i]` (Euler)/`lock_scale[i]` true stays as it was **[I]**; `clear_delta` →
    also `delta_location`/`delta_rotation_euler` and `delta_rotation_quaternion`/`delta_scale` to the
    neutral values. `{"FINISHED"}`.

Errors (as seen by the caller via `quartz.ops.call`): `PropertyTypeError` (`'enum "POSE" not found in
('` **[O]**); `PollFailedError` (`"failed, context is incorrect"`: `mode_set` with no active object, operators
with an OM poll in `EDIT_MESH`); `OperatorFailedError` (`"multi user"`, `"is not supported in Quartz"`,
`"Loop in parents"`).

#### 2.7.4 `quartz/operators/mesh.py`

```python
CLASSES: tuple[type, ...]                 # the 11 classes, in the order of the introduction table
PRIMITIVE_NAMES: Mapping[str, str] = {"plane": "Plane", "cube": "Cube", "circle": "Circle", "uv_sphere": "Sphere",
    "ico_sphere": "Icosphere", "cylinder": "Cylinder", "cone": "Cone", "grid": "Grid", "torus": "Torus"}   # [O] primitives judge
MONKEY_POLL_MESSAGE: str = "Suzanne geometry is not available in Quartz"                                  # own wording
# kit = enter_editmode_prop(), align_prop(), location_prop(), rotation_prop(), scale_prop() (§2.7.2), in this order, after the operator's own props
class MESH_OT_primitive_plane_add(Operator):    # size: distance_prop(2.0); calc_uvs: Bool True; kit
class MESH_OT_primitive_cube_add(Operator):     # size: distance_prop(2.0); calc_uvs; kit
class MESH_OT_primitive_circle_add(Operator):   # vertices: Int 32 [3, 10000000] soft [3, 500]; radius: distance_prop(1.0);
                                                # fill_type: Enum NOTHING|NGON|TRIFAN = "NOTHING"; calc_uvs; kit
class MESH_OT_primitive_uv_sphere_add(Operator):# segments: Int 32 [3, 100000] soft [3, 500]; ring_count: Int 16 (same); radius; calc_uvs; kit
class MESH_OT_primitive_ico_sphere_add(Operator):  # subdivisions: Int 2 [1, 10] soft [1, 8]; radius; calc_uvs; kit
class MESH_OT_primitive_cylinder_add(Operator): # vertices (as circle); radius; depth: distance_prop(2.0);
                                                # end_fill_type: Enum NOTHING|NGON|TRIFAN = "NGON"; calc_uvs; kit
class MESH_OT_primitive_cone_add(Operator):     # vertices; radius1: distance_prop(1.0); radius2: distance_prop(0.0, soft_min=0.0); depth; end_fill_type; calc_uvs; kit
class MESH_OT_primitive_grid_add(Operator):     # x_subdivisions, y_subdivisions: Int 10 [1, 10000000] soft [1, 1000]; size: distance_prop(2.0); calc_uvs; kit
class MESH_OT_primitive_torus_add(Operator):    # bl_options {"PRESET","REGISTER","UNDO"} [O]; NO kit (Python operator form from the dump), in this order:
    # align: align_prop(); location: FloatVector TRANSLATION/LENGTH 3, limits and soft ±FLOAT_MAX, step 3, precision 2, NO flags;
    # rotation: FloatVector EULER/ROTATION 3 (same, NO flags); major_segments: Int 48 [3, 256] soft [3, 256];
    # minor_segments: Int 12 [3, 256] soft [3, 256]; mode: Enum MAJOR_MINOR|EXT_INT = "MAJOR_MINOR";
    # major_radius 1.0, minor_radius 0.25, abso_major_rad 1.25, abso_minor_rad 0.75: Float DISTANCE/LENGTH [0, 10000] soft [0, 100] step 3 precision 2;
    # generate_uvs: Bool True
class MESH_OT_primitive_monkey_add(Operator):   # size: distance_prop(2.0); calc_uvs; kit; poll ALWAYS false with MONKEY_POLL_MESSAGE
class MESH_OT_select_all(Operator):             # action: Enum TOGGLE|SELECT|DESELECT|INVERT = "TOGGLE" (HIDDEN, SKIP_SAVE) [I]; poll: context.mode == "EDIT_MESH" [I]
```

All have `bl_options == {"REGISTER", "UNDO"}` **[O]**, except the torus (above).

1. **Primitives** (common `execute`, no poll except the monkey), in this order:
   1. `context.mode == "EDIT_MESH"` → `{"ERROR"}` report with `"edit mode"` (adding to the mesh
      being edited is not supported) and `{"CANCELLED"}` **[I]**.
   2. `geo = quartz.geometry.<function>(...)` with the parameters of the same name (§1.5.4): `plane(size,
      calc_uvs=)`, `cube(size, calc_uvs=)`, `circle(vertices, radius, fill_type, calc_uvs=)`,
      `uv_sphere(segments, ring_count, radius, calc_uvs=)`, `ico_sphere(subdivisions, radius,
      calc_uvs=)`, `cylinder(vertices, radius, depth, end_fill_type, calc_uvs=)`, `cone(vertices,
      radius1, radius2, depth, end_fill_type, calc_uvs=)`, `grid(x_subdivisions, y_subdivisions,
      size, calc_uvs=)`, `torus(major_segments, minor_segments, R, r, calc_uvs=generate_uvs)` with
      `mode == "MAJOR_MINOR"` → `R, r = major_radius, minor_radius`; `"EXT_INT"` → `R =
      (abso_major_rad + abso_minor_rad) / 2`, `r = (abso_major_rad - abso_minor_rad) / 2` **[I]**.
      Out-of-range values already arrive clamped by the props' coercion **[O]** (`vertices=2` →
      3). `ValueError` from `quartz.geometry` (parameters that clamping does not cover, e.g. `r <= 0` in
      `EXT_INT`) → `{"ERROR"}` report with `str(exc)` and `{"CANCELLED"}` **[I]** (nothing changed).
   3. Any other non-object mode → `ensure_object_mode(context)`.
   4. `me = context.blend_data.meshes.new(PRIMITIVE_NAMES[k])`; `me.q_set_geometry(geo)`.
   5. `ob = object_data_add(context, me, name=PRIMITIVE_NAMES[k], matrix=operator_add_matrix(self,
      context))` — the object and the mesh each get unique names in their own collection (factory: `Cube.001` and
      `Cube.001` **[O]**).
   6. `enter_editmode` (only the primitives with the kit) → `ob.q_set_mode("EDIT")` **[I]**. `{"FINISHED"}`.
   Facts **[O]** (`primitives` judge, each default primitive added in the factory and removed
   afterwards, object and mesh): v/e/f/corner counts from §1.5.4; object names = mesh names =
   `Plane`, `Cube.001`, `Circle`, `Sphere`, `Icosphere`, `Cylinder`, `Cone`, `Grid`, `Torus`;
   `uv_layers == ["UVMap"]`; no polygon with `use_smooth`; the new object is the active one and the only
   one selected.
2. **`primitive_monkey_add`**: `poll` calls `cls.poll_message_set(MONKEY_POLL_MESSAGE)` and returns
   `False` (divergence 7 of ARCHITECTURE §13; in Blender the poll is true **[O]**). `execute`
   returns `{"CANCELLED"}` (unreachable through `quartz.ops`).
3. **`select_all(action)`**: `pairs = edit_meshes(context)`; `TOGGLE` → `DESELECT` if any mesh in
   `pairs` has a selected vertex, otherwise `SELECT` (decided once for all) **[I]**; for each
   `(ob, me)`: writes `select` of `me.vertices`, `me.edges` and `me.polygons` via
   `foreach_get/foreach_set` (elements with `hide` true are left unselected in `SELECT` and
   untouched in `INVERT`) **[I]**. `{"FINISHED"}`.

Errors: `PollFailedError` (`f"Operator {P}.ops.mesh.primitive_monkey_add.poll()"` +
`"not available in Quartz"`, `P` = `settings.api_prefix`; `mesh.select_all` outside edit mode:
`"failed, context is incorrect"`); `OperatorFailedError` (`"edit mode"`).

#### 2.7.5 `quartz/operators/transform.py`

```python
CLASSES: tuple[type, ...]                 # TRANSFORM_OT_translate, TRANSFORM_OT_rotate, TRANSFORM_OT_resize
ORIENT_TYPES: tuple[str, ...] = ("GLOBAL", "LOCAL", "NORMAL", "GIMBAL", "VIEW", "CURSOR", "PARENT")   # [O] translate items
class TRANSFORM_OT_translate(Operator):  # {"BLOCKING","REGISTER","UNDO"} [O]; the 32 props from the dump
    # used: value (FloatVector TRANSLATION/LENGTH, 3, precision 5), orient_type, orient_matrix (Float MATRIX 3x3, HIDDEN|SKIP_SAVE),
    #         orient_matrix_type, constraint_axis (BoolVector XYZ, 3), cursor_transform
class TRANSFORM_OT_rotate(Operator):     # same; the 25 props from the dump; used: value (Float ANGLE/ROTATION), orient_axis (X|Y|Z = "Z", SKIP_SAVE),
                                         # orient_type, orient_matrix, constraint_axis, center_override (FloatVector XYZ, 3)
class TRANSFORM_OT_resize(Operator):     # same; the 28 props from the dump; used: value (FloatVector XYZ, 3, default (1,1,1)),
                                         # orient_type, orient_matrix, constraint_axis, center_override
```

`orient_type`/`orient_matrix_type` of `rotate` and `resize` use the static `ORIENT_TYPES` items
(default `"GLOBAL"`; the dump captures them empty because they are dynamic in Blender **[O]**, §2.7.8). All
the other props (proportional, snap, `mirror`, `release_confirm`, `use_accurate`, …) are declared
as in the dump, accepted and ignored **[I]**. No poll (true in the factory, **[O]**
`ops.poll_in_background`).

1. **Orientation** `O` (3×3, columns = axes in world coordinates): `orient_matrix` with
   `is_property_set` → that matrix, read as a `Matrix` (row i of the array = row i of the `Matrix`,
   §2.2.1) **[I]**; otherwise by `orient_type`: `GLOBAL`/`VIEW` → identity; `LOCAL`/`NORMAL`/`GIMBAL`
   → normalized columns of the 3×3 of `ob.matrix_world`; `CURSOR` → 3×3 of `scene.cursor.matrix`;
   `PARENT` → that of `ob.parent.matrix_world` (identity without a parent) **[I]**. When `O` depends on the
   object (`LOCAL`, `NORMAL`, `GIMBAL`, `PARENT`), it — and the matrix `M` of rule 4 — is computed per
   object (in edit mode, by the object that owns the mesh).
2. **Targets** in `"OBJECT"`: `top_level_objects(context.selected_editable_objects)`; empty →
   `{"CANCELLED"}`. In `"EDIT_MESH"`: vertices with `select` (and without `hide`) of the meshes in
   `edit_meshes(context)`; none → `{"CANCELLED"}`. Any other mode → `{"CANCELLED"}` **[I]**.
3. **Pivot** `p` (rotate/resize): `center_override` with `is_property_set` → it; otherwise
   `scene.tool_settings.transform_pivot_point`: `MEDIAN_POINT` (default **[O]**) → mean of the world
   positions of the targets (object origins; vertices in edit mode); `BOUNDING_BOX_CENTER` → center of the
   box of those positions; `CURSOR` → `scene.cursor.location`; `ACTIVE_ELEMENT` → origin of the active object
   (in edit mode, the mean); `INDIVIDUAL_ORIGINS` → each object around its own origin (in edit mode, the
   mean) **[I]**.
4. **World matrix** `M` applied on the left: translate `M = T(O · v)`, with `v = value` and, if any
   `constraint_axis` is true, the components of the false axes zeroed **[I]**; rotate `M =
   T(p) · R(axis, value) · T(−p)`, axis = column of `O` for `orient_axis` (or the only true axis of
   `constraint_axis`, when exactly one), positive angle by the right-hand rule **[I]**;
   resize `M = T(p) · O · diag(f) · Oᵀ · T(−p)` with `f = value` and, when constrained, 1 on the false
   axes **[I]**.
5. **Objects**: `ob.matrix_world = M @ ob.matrix_world` (the write decomposes into the basis respecting
   the parent and `matrix_parent_inverse`, §2.2.6); then the components with `lock_location`,
   `lock_rotation` (Euler) and `lock_scale` go back to their previous value **[I]**.
6. **Edit mode**: for each `(ob, me)`, `W = ob.matrix_world`; selected local position `x` becomes
   `W.inverted_safe() · M · W · x`; written with `me.vertices.foreach_set("co", ...)` (stamps
   `"GEOMETRY"`, §2.3).
7. `cursor_transform` (translate) → only `scene.cursor.location += O · v` (with `O` without an object:
   `LOCAL`/`NORMAL`/`GIMBAL`/`PARENT` are identity); nothing else changes **[I]**.
8. Returns `{"FINISHED"}` when something was transformed.

Errors: none of its own (impossible cases return `{"CANCELLED"}`).

#### 2.7.6 `quartz/operators/ed.py`

```python
CLASSES: tuple[type, ...]                 # ED_OT_undo, ED_OT_redo, ED_OT_undo_push, ED_OT_undo_history
UNDO_DISABLED_MESSAGE: str                # contains "Undo disabled at startup in background-mode" and "ed.undo_push()" [O]
class ED_OT_undo(Operator):          # bl_options set() [O]; no props
class ED_OT_redo(Operator):          # set() [O]; no props
class ED_OT_undo_push(Operator):     # {"INTERNAL"} [O]; message: StringProperty(default="") [I]
class ED_OT_undo_history(Operator):  # set() [O]; item: IntProperty(default=0, min=0) [I]
```

`u = quartz.session.current().undo` (import inside the functions).

1. `ED_OT_undo.poll`, `ED_OT_redo.poll` and `ED_OT_undo_history.poll`: `u.enabled`; false →
   `cls.poll_message_set(UNDO_DISABLED_MESSAGE)` and `False`. In a freshly created session all three polls are
   false **[O]** (`undo_and_handlers` probe of the dump: `ed_undo_poll`, `ed_redo_poll`,
   `ed_undo_history_poll` false), and also after `Session.reset` (which clears undo, §2.6.4) **[I]**;
   `quartz.ops.ed.undo()` raises `PollFailedError` with `f"Operator {P}.ops.ed.undo.poll() "` + the
   message **[O]** (`ed_undo_call`).
2. `ED_OT_undo_push`: no poll (true **[O]**, `ed_undo_push_poll`); `execute` →
   `u.push(self.message)`; `{"FINISHED"}` **[O]** (`ed_undo_push_call`). It turns undo on (§2.6.4); since it
   has no `UNDO` in `bl_options`, `quartz.ops` does not push another step.
3. `ED_OT_undo.execute` → `{"FINISHED"}` if `u.undo()`, otherwise `{"CANCELLED"}` **[I]**;
   `ED_OT_redo` likewise with `u.redo()`; `ED_OT_undo_history` → `u.jump(self.item)` (`False` →
   `{"CANCELLED"}`) **[I]**.
4. Verifiable cycle: `ed.undo_push(message="base")`, `mesh.primitive_cube_add()` (pushes
   `bl_label`), `ed.undo()` → the copy disappears (tombstone) and `u.history()[u.index()] == "base"`;
   `ed.redo()` → the same Python object comes back (identity, D15).

Errors: `PollFailedError` (`"Undo disabled at startup in background-mode"` **[O]**).

#### 2.7.7 `quartz/operators/wm.py`

```python
CLASSES: tuple[type, ...]       # the 7 classes, in the order of the introduction table; bl_options set() [O], except call_menu/call_menu_pie {"INTERNAL"} [O]
# _FileSelectProps (private mixin, plain class with no base; annotations collected before those of the subclass, §1.6.6) — fields [I]
# (types and items in the style of the dump's file operators, e.g. object.empty_image_add; defaults chosen for .qz), in dump order:
#   filepath: String FILE_PATH "" (maxlen 1024, SKIP_SAVE); hide_props_region: Bool True; check_existing: Bool True;
#   filter_blender: Bool True; filter_backup, filter_image, filter_movie, filter_python, filter_font, filter_sound, filter_text,
#   filter_archive, filter_btx, filter_alembic, filter_usd, filter_obj, filter_volume: Bool False; filter_folder: Bool True;
#   filter_blenlib: Bool False; filemode: Int 8 [1, 9]; display_type: Enum DEFAULT|LIST_VERTICAL|LIST_HORIZONTAL|THUMBNAIL = "DEFAULT";
#   sort_method: Enum DEFAULT|FILE_SORT_ALPHA|FILE_SORT_EXTENSION|FILE_SORT_TIME|FILE_SORT_SIZE|ASSET_CATALOG = "DEFAULT"
#   (all except filepath: HIDDEN + SKIP_SAVE)
class WM_OT_read_factory_settings(Operator):  # use_factory_startup_app_template_only: Bool False (HIDDEN|SKIP_SAVE); app_template: String ""
                                              # (HIDDEN|SKIP_SAVE); use_empty: Bool False
class WM_OT_read_homefile(Operator):          # filepath: String FILE_PATH "" (HIDDEN|SKIP_SAVE); load_ui: True; use_splash: False;
                                              # use_factory_startup: False; use_factory_startup_app_template_only: False; app_template: ""; use_empty: False
class WM_OT_save_as_mainfile(_FileSelectProps, Operator):  # + compress: False; relative_remap: True; copy: Bool False (SKIP_SAVE);
                                                           #   show_save_modified_images_dialog: False
class WM_OT_save_mainfile(_FileSelectProps, Operator):     # + compress: False; relative_remap: False; exit: False; incremental: False;
                                                           #   show_save_modified_images_dialog: False
class WM_OT_open_mainfile(_FileSelectProps, Operator):     # + load_ui: True; use_scripts: False; display_file_selector: True;
                                                           #   state: Int 0 (HIDDEN|SKIP_SAVE)
class WM_OT_call_menu(Operator):              # name: String "" [I]
class WM_OT_call_menu_pie(Operator):          # name: String "" [I]
```

All without a poll (true) **[I]**; all fields besides `type` are **[I]** (common rule 2). Paths
go through `quartz.path.abspath` (`"//"` relative to the current file, §1.1.6). "`.blend` path" =
`.blend` extension, case-insensitive → `{"ERROR"}` report with `".blend"` and
`"not supported"` and `{"CANCELLED"}`, checked before calling `quartz.io` (`.blend` is neither read nor
written, D16, §2.6.5); any other extension is treated as `.qz`. `OSError`/
`FileFormatError` exceptions from `quartz.io` → `{"ERROR"}` report with `str(exc)` and `{"CANCELLED"}`. `data` =
`context.blend_data`.

1. **`read_factory_settings`** → `quartz.session.reset(template="empty" if use_empty else
   "default")` **[I]**; the registry (including add-ons) does not change; `{"FINISHED"}`.
2. **`read_homefile`**: `use_factory_startup` or `filepath == ""` → as (1); otherwise `.blend` path →
   error; otherwise `quartz.io.load_qz(path)` followed by `data.q_set_filepath("")` and `data.q_mark_clean()`
   (the startup file opens "untitled") **[I]**; `{"FINISHED"}`.
3. **`save_as_mainfile`**: `path = filepath` or, if empty, `data.filepath`; still empty → `{"ERROR"}`
   with `"no file path"` + `{"CANCELLED"}` **[I]**; `.blend` → error; otherwise `quartz.io.save_qz(path,
   copy=copy)` (with `copy` false, `data.filepath` becomes `path`, §2.6.5); `{"FINISHED"}`.
   `check_existing`, `compress` and `relative_remap` are ignored (always overwrites) **[I]**.
4. **`save_mainfile`**: `incremental` → `{"ERROR"}` with `"incremental save is not supported"` +
   `{"CANCELLED"}` **[I]** (checked first); otherwise as (3) with `copy=False`; `exit` is ignored
   (the process never terminates because of an operator) **[I]**.
5. **`open_mainfile`**: empty `filepath` → `"no file path"`; `.blend` → error; otherwise
   `quartz.io.load_qz(path)` (non-persistent handlers cleared, windows re-pointed, undo cleared,
   `data.filepath == path`, §2.6.5); `use_scripts`, `load_ui`, `display_file_selector`, `state`
   ignored **[I]**; `{"FINISHED"}`.
6. **`call_menu(name)` / `call_menu_pie(name)`**: `cls = quartz.registry.lookup(name)` (with compat
   active, the missing-class resolver creates placeholders, §3.1.1); `None` or not a subclass of
   `quartz.types.ui.Menu` → `{"ERROR"}` `f'Menu "{name}" not found'` + `{"CANCELLED"}` **[I]**. Otherwise
   `r = quartz.ui.draw_menu(cls, context)` (an exception in `draw` becomes `LayoutIssue("DRAW_EXCEPTION")`,
   never propagates, §2.5.6) and `context.window_manager.q_ui_requests.append((idname_py, name, r))`
   with `idname_py` = `"wm.call_menu"` or `"wm.call_menu_pie"` (item format fixed here;
   `Session.reset` empties the list, §2.6.1); returns `{"INTERFACE"}` **[I]**.

Errors (via `quartz.ops.call`): `OperatorFailedError` with `".blend"`, `"no file path"`,
`"incremental save is not supported"`, `"not found"` or the text of `FileFormatError`.

#### 2.7.8 Tests

All in `tests/unit/operators/`, with the `qz`/`qz_empty` fixtures (§1.1.2; the session already has the
built-ins registered), except where indicated. **[O]** values come from the `blender_facts` (judge) and
`blender_dump` (dump) fixtures, never copied by hand; floats with `pytest.approx(abs=1e-5)`. No test
imports L3. Until `l2-runtime`, `l2-idmodel`, `l2-datablocks` and `l2-registry-ui` exist, only the
isolated part of `test_common.py` passes; the rest passes at the L2 gate (§0.6, §2.0.5).

- `test_builtin_registry.py`: `len(builtin_classes()) == 43`, stable order and identity across
  calls; the `bl_idname`s == the introduction table of §2.7 (as a set and per module, via the
  `CLASSES` of each module); `bl_label` and `bl_description` are non-empty `str`; each class
  registered in the session with `registry.owner_of(c) == "quartz.builtin"`; `registry.counts_by_base()`
  does not count them; `register_builtin()` twice changes nothing (no error); `unregister_builtin()` →
  `registry.operator_class("object.select_all") is None` and `quartz.ops.object.select_all()` raises
  `OperatorNotFoundError` (`"could not be found"`); `register_builtin()` again restores; `is_builtin`
  with a class, idname_py, RNA name, a foreign name (`False`), a registered user operator (`False`) and
  `42` (`False`); `import quartz.operators` registers nothing and does not import `quartz.session`
  (checked in a clean process via `subprocess` with `-I` and the root `sys.path`).
- `test_common.py`: (isolated, no session: `types.SimpleNamespace` as context with
  `scene.cursor.location`/`matrix`) `add_matrix` with the cursor at `(1, 2, 3)` and no args → cursor
  translation; explicit `location` beats the cursor; `rotation=(0, 0, π/2)` → `Matrix.Rotation(π/2, 4,
  "Z")`; `align="CURSOR"` uses the cursor rotation and explicit `rotation` ignores it; `align="VIEW"` →
  identity; `scale`; `align="X"` → `ValueError` (`'align "X" not in ('`); prop kit:
  `to_float32(rotation_prop().keywords["soft_max"]) == 6.2831854820251465`, each call returns a
  new object, `align_prop(hidden=True).keywords["options"] == {"HIDDEN"}`. (with `qz`)
  `object_data_add` links into `context.collection` (`"Collection"` in the factory), makes the new object active
  and the only one selected, applies `matrix`, name `"Empty"` without data; with `qz_empty` it links into the master collection;
  `deselect_all`; `top_level_objects` drops a child and grandchild whose ancestor is in the list and keeps
  the order; `scene_collections_of`; `ensure_object_mode` leaves `EDIT`; `edit_meshes` is empty in object
  mode and, in edit mode, returns `[(Cube, mesh)]` with `q_edit_data is None`.
- `test_mode_set.py`: the **[O]** facts of the `modes` judge (`EDIT_MESH`, `objects_in_mode == ["Cube"]`,
  `is_editmode`, returns to `OBJECT`, `toggle` twice); `mode="POSE"` → `PropertyTypeError` whose text
  contains that of `blender_facts["modes"]["pose_on_mesh"]` without the `"TypeError: "` prefix; poll with no active object →
  `PollFailedError` (`"failed, context is incorrect"`); active empty with `mode="EDIT"` →
  `PropertyTypeError` (`'enum "EDIT" not found in (\'OBJECT\')'`); `editmode_toggle` enters and leaves;
  `mode_set` with another mesh also selected takes both to `EDIT` (`objects_in_mode` with
  both, active first); the same mode without `toggle` → `{"FINISHED"}` with no change; `object.select_all`
  in edit mode → `PollFailedError`.
- `test_object_ops.py`: `select_all` reproduces `blender_facts["ops.select_all"]` after deselecting everything;
  `SELECT`, `DESELECT`, `hide_select` excludes; `select_by_type(type="CAMERA")` with and without `extend`;
  `delete` removes the `Cube`, leaves the mesh `"Cube"` with `users == 0`, prints `"Deleted 1 object(s)"`
  (capsys) and returns `{"CANCELLED"}` with no selection; `use_global`; `duplicate` reproduces
  `blender_facts["ops.duplicate"]` (including `linked=True`); parent and child duplicated together → new child
  points to the new parent; `transform_apply` on a Cube with loc `(1,2,3)`, rot Z 90°, scale 2:
  neutral channels, `q_bounds()` transformed and world positions of the vertices equal to the previous ones;
  `scale=True` alone keeps loc/rot; child keeps `matrix_world`; shared mesh →
  `OperatorFailedError` (`"multi user"`) with no change, and with `isolate_users=True` the mesh is copied;
  negative scale with `corrective_flip_normals` flips normals; light → `"not supported"` on stdout and
  untouched; `shade_smooth`/`shade_flat` change `use_smooth` of all polygons and respect
  `keep_sharp_edges` (`sharp_edge` attribute preserved or removed); `object.add` (`EMPTY` with
  `radius=3` → `empty_display_size == 3`, `MESH`, `CAMERA`, `LIGHT`), `type="ARMATURE"` →
  `OperatorFailedError` (`"is not supported in Quartz"`) without leaving edit mode or creating anything;
  `empty_add(type="CUBE")`; `camera_add` does not change `scene.camera`; `light_add(type="SUN")` → object
  `"Sun"` with `SunLight`; given `location` vs moved cursor; `parent_set` (child's world transform preserved with
  `keep_transform`), cycle → `"Loop in parents"`, `type="BONE"` → `"not supported"`; `parent_clear` in the
  three types; `location_clear`/`rotation_clear`/`scale_clear` with locks and `clear_delta`;
  `temp_override(selected_objects=[light])` makes `delete` act only on the light; with
  `qz.undo.push("x")` beforehand, a `select_all` adds the `bl_label` step (§2.1.8(9)).
- `test_mesh_primitives.py`: for each default primitive, in the factory, reproduces `blender_facts
  ["primitives"][k]` (v/e/f/l, object and mesh names, `uv`, `smooth` false) removing the object and
  mesh after each one; local box equal to the judge's (except `ico_sphere`: only inside the sphere of
  radius 1, §1.5.4); explicit `location`, `rotation`, `scale` reach `matrix_world`; without `location` the
  object is born at the cursor; `primitive_circle_add(vertices=2)` → circle with 3 vertices (clamped);
  `fill_type`/`end_fill_type` with the counts from §1.5.4; `torus(mode="EXT_INT", abso_major_rad=1.5,
  abso_minor_rad=0.5)` → box ±1.5 in XY and ±0.5 in Z; `torus(mode="EXT_INT", abso_major_rad=0.5,
  abso_minor_rad=0.5)` → `OperatorFailedError` with no new mesh; `calc_uvs=False` → no `"UVMap"`;
  `enter_editmode=True` → `context.mode == "EDIT_MESH"`; in edit mode → `OperatorFailedError`
  (`"edit mode"`); `quartz.ops.mesh.primitive_monkey_add.poll()` false and the call →
  `PollFailedError` (`"not available in Quartz"`); `mesh.select_all` (`SELECT`, `DESELECT`, `TOGGLE`,
  `INVERT`) in edit mode counting `count_selected_items()`; outside edit mode → `PollFailedError`.
- `test_transform_ops.py`: `translate(value=(1, 2, 3))` on the selected Cube; `constraint_axis=(True,
  False, False)` moves only in X; `orient_type="LOCAL"` on an object rotated 90° in Z; child and parent
  selected → the child moves only once; `lock_location` respected; `rotate(value=π/2,
  orient_axis="Z")` on an object at `(1, 0, 0)` with `CURSOR` pivot at the origin → `(0, 1, 0)` and Z rotation
  `+π/2` **[I]**; `MEDIAN_POINT` with two objects; `INDIVIDUAL_ORIGINS`; `center_override`;
  `resize(value=(2, 2, 2))` with `MEDIAN_POINT` pivot; `rotate(orient_type="LOCAL")` accepted (static
  items); `cursor_transform=True` moves only the cursor; no selection → `{"CANCELLED"}`; in edit mode, only
  the selected vertices change (via `q_geometry.positions`) and the mesh stamps `"GEOMETRY"`
  (`q_dirty_since`).
- `test_ed_ops.py`: in the new session, `quartz.ops.ed.<op>.poll()` reproduces the values of
  `blender_dump["probes"]["undo_and_handlers"]` (`ed_undo_poll`, `ed_redo_poll`,
  `ed_undo_history_poll` false; `ed_undo_push_poll` true); `ed.undo()` → `PollFailedError`
  containing `"Undo disabled at startup in background-mode"` and `"ed.undo_push()"` **[O]**;
  `ed.undo_push()` → `{"FINISHED"}` **[O]** and turns undo on (`qz.undo.enabled`); the cycle of §2.7.6(4)
  with identity preserved; `ed.undo()` with no previous step → `{"CANCELLED"}`;
  `ed.undo_history(item=0)`; `wm.read_factory_settings()` turns undo off again.
- `test_wm_ops.py`: `save_as_mainfile(filepath=str(tmp_path / "a.qz"))` → file exists,
  `quartz.data.filepath` updated, `is_dirty` false; `copy=True` does not change `filepath`;
  `save_mainfile()` rewrites to the same path and, without a path, → `"no file path"`; `incremental=True` →
  `OperatorFailedError`; `open_mainfile` after deleting the Cube brings the Cube back (counts) and clears the non-persistent
  handler; nonexistent file → `OperatorFailedError`; `.blend` (also `.BLEND`) in save and
  open → `OperatorFailedError` with `".blend"` and no file created; `read_factory_settings` restores
  the factory state after changes and `use_empty=True` → no objects; `read_homefile(filepath=...)` leaves
  `filepath == ""`; `call_menu(name=...)` of a `Menu` registered in the test → `{"INTERFACE"}`, `draw`
  called once and item `("wm.call_menu", name, DrawResult)` in `wm.q_ui_requests`; menu whose `draw`
  raises → still `{"INTERFACE"}` with `DRAW_EXCEPTION`; unknown name → `OperatorFailedError`
  (`"not found"`); `call_menu_pie` likewise (item with `"wm.call_menu_pie"`).
- `test_operator_schema.py`: for each class `c` of `builtin_classes()`, with `e =
  blender_dump["ops"]["submodules"][mod][op]`: `registry.operator_rna_name(c.bl_idname) ==
  e["bl_idname"]`; `set(c.bl_options) == set(e["bl_options"])` and
  `quartz.ops.<mod>.<op>.bl_options` equal; `quartz.testing.rna_schema_diff(c.q_properties_class(),
  e["props"], require_all=True, divergences=...) == []`. The module defines `DIVERGENCES` (§2.4.5) with,
  at a minimum: `"OBJECT_OT_mode_set.mode.items"` ("dynamic enum by active object type; the dump lists
  the 14 static ones"), `"TRANSFORM_OT_rotate.orient_type.items"`,
  `"TRANSFORM_OT_rotate.orient_matrix_type.items"`, `"TRANSFORM_OT_resize.orient_type.items"`,
  `"TRANSFORM_OT_resize.orient_matrix_type.items"` ("dynamic enum captured empty in the dump; Quartz
  uses the 7 items of translate"). For an operator outside `blender_dump["ops"]["detail_ops"]`, the test
  adds at run time (local copy, without mutating the module), for each prop of the dump, the
  keys `f"{T}.{id}.{field}"` with `field` in `("subtype", "unit", "array_length",
  "array_dimensions", "default", "min", "max", "soft_min", "soft_max", "step", "precision", "items",
  "length_max", "fixed_type", "flags")` (reason "dump without detail: only the type is compared"); thus
  `type` is always checked. Also: every idname in the table of §2.7 exists in the dump, and no
  built-in declares a prop outside the dump (covered by `require_all` + the `q_` rule). Finally,
  `quartz.operators.object.OBJECT_TYPE_IDS == quartz.types.object.OBJECT_TYPES` (with
  `quartz.types.object` imported inside the test) and `len(DUPLICATE_MODE_IDS) == 32`, equal to the
  items of `object.duplicate.mode` in the dump.

---

## 3. Layer 3: Compat, loader and CLI

### 3.0 Overview and L3 gate

Layer 3 delivers Path A (the `compat/` shims that let Blender add-ons run on top of Quartz), the native
extensions of `bpy_extras` and `bmesh`, the add-on and extension loader, the CLI, the sweep and the
goldens. L3 `quartz.*` modules import any `quartz.*`; files in `compat/` import only stdlib, `quartz.*`
and other shims, and **never numpy** (§0.5).

#### 3.0.1 Tasks, sections and dependencies

| Section | Task | Modules | Uses from L3 |
|---|---|---|---|
| §3.1 | `l3-compat-bpy` | `quartz.compat` (+ `profile`, `blender_5_2.json`), shims `bpy`, `idprop`, `rna_prop_ui`, `bl_math`, `bl_ui`, `bl_operators` | nothing |
| §3.2 | `l3-compat-math-extras` | `quartz.extras`, shims `mathutils`, `bpy_extras`, `gpu`, `gpu_extras`, `blf`, `aud` | nothing |
| §3.3 | `l3-bmesh` | `quartz.bmesh`, shim `bmesh` | nothing |
| §3.4 | `l3-addons` | `quartz.addons`, shim `addon_utils`, add-on fixtures | `quartz.compat`, only for Blender add-ons (§0.6) |
| §3.5 | `l3-cli-sweep` | `quartz.cli`, `quartz.sweep`, `quartz.scan`, tools, goldens, `README.md`, `docs/ROADMAP.md` | all |

Owners of the top-level modules of `compat/`: `bpy`, `idprop`, `rna_prop_ui`, `bl_math`, `bl_ui`,
`bl_operators` → `l3-compat-bpy`; `mathutils`, `bpy_extras`, `gpu`, `gpu_extras`, `blf`, `aud` →
`l3-compat-math-extras`; `bmesh` → `l3-bmesh`; `addon_utils` → `l3-addons`. Blender's `imbuf` module
(dump `extras.imbuf`) has no shim in this milestone (out of scope; divergence in §3.1.7, item
5; `TRACKED_ROOTS` of §3.5.3 does not include it, to keep comparability with `data/bpy_usage.json`).
The `bl_ext` and
`qz_ext` packages are not files: they are synthesized in `sys.modules` by `quartz.addons` (§3.4.4).

Thinness rule (D1; `tests/arch/test_compat_thin.py`): a shim only re-exports objects from `quartz`
(identity) or implements a Blender quirk (version 5.2.2, UI placeholders, GPU/audio stubs, minimal
`bl_ui`/`bl_operators` mixins, the `addon_utils` facade). Everything else lives in `quartz`.

#### 3.0.2 Import effects allowed in Layer 3 (closed list)

| Import | Effect |
|---|---|
| shim `compat/mathutils` | `quartz.extras.install_adapters()` (`BVHTree.FromObject` adapter, §3.2.1) |
| shim `compat/bmesh` | `quartz.bmesh.install_adapters()` (`BVHTree.FromBMesh` adapter and `quartz.types.mesh.set_editmode_hooks`, §3.3.1) |
| other shims | none beyond re-exporting (the profile is loaded lazily) |

No L3 `quartz.*` module has an import effect (all L3 test directories
(`tests/addons`, `arch`, `bmesh`, `cli`, `compat`, `contract`, `extras`, `golden`, `sweep`) run
before `tests/unit`, whose L1 tests verify the "adapter not installed" behavior of
§1.4.9). Adapters and hooks installed by L3 enter only through: the two shims above (with the compat
active, or with `compat_dir()` in `sys.path`, §3.2.6 rule 4); `quartz.cli.main` (at the start);
`quartz.bmesh.from_edit_mesh` (ensures the `flush` hook on the first call); or an explicit call to
`install_adapters()`. Exiting `quartz.testing.isolated()` returns them to the default:
`quartz.math.bvhtree.set_object_adapter(None)`, `quartz.math.bvhtree.set_bmesh_adapter(None)` and
`quartz.types.mesh.set_editmode_hooks()`; `quartz.compat.deactivate()` does the same only for those
installed by a shim imported during that activation (§3.1.1, Deactivation, step 5).
`quartz.compat` only hooks in at `activate()`; `quartz.addons` only touches `sys.path`/`sys.modules` inside
`ensure_extension_packages`, `sync_sys_path`, `enable` (and its callers) and `q_reset` (§3.4,
rule 2); `discover` never does.

#### 3.0.3 Compat activation (sequence of `quartz.compat.activate`)

Owner: `l3-compat-bpy` (§3.1.1). `activate(*, strict=False, blender_version=None)`:

1. There is a `"bpy"` in `sys.modules` that did not come from `quartz.app.paths.compat_dir()` → `CompatError` with
   `"already loaded"`.
2. Already active → only updates strictness (`settings.lenient_ui = not strict`) and returns.
3. Saves the current values of `settings.api_prefix/lenient_ui/record_missing` and of the hooks
   `note_missing`/`repr_root`.
4. `sys.path.insert(0, str(compat_dir()))` if absent.
5. `settings.api_prefix = "bpy"`; `settings.lenient_ui = not strict`; `settings.record_missing =
   True`.
6. `hooks.install(note_missing=quartz.compat.note_missing, repr_root=lambda: "bpy")`.
7. `quartz.registry.set_missing_type_resolver(quartz.compat.resolve_type)`.
8. `importlib.import_module("bpy")` (the shim); failure undoes steps 4–7 and propagates.

`deactivate()`: normative sequence in §3.1.1 (Deactivation); idempotent. The `bpy` and `bpy_lenient` fixtures (§1.1.2) are `activate(strict=True)` and
`activate(strict=False)`.

Strict vs. lenient (both record everything in `missing_symbols()`): names that exist in the profile
resolve in both modes (UI placeholder or inert phantom type); unknown names in UI
form (`*_MT_*`, `*_PT_*`, `*_HT_*`, `*_UL_*`) are synthesized only in lenient mode; in strict mode,
unknown → `AttributeError`, as in Blender.

#### 3.0.4 Loader cycle (sequence of `AddonManager.enable`/`disable`)

Owner: `l3-addons` (§3.4.5). `enable(module_name, *, default_set=False, persistent=False,
refresh_handled=False, handle_error=None)`:

1. Target is a Blender add-on (does not start with `"qz_ext."`) and the compat is inactive →
   `quartz.compat.activate(strict=False)` (the loader does not deactivate it afterwards; so tests that
   enable Blender add-ons MUST use the `bpy`/`bpy_lenient` fixtures).
2. `sync_sys_path()`; `ensure_extension_packages()`.
3. Module already in `sys.modules` and enabled → `unregister()` (an error goes to `handle_error`) and, if the
   mtime changed, `importlib.reload` **[L]**.
4. `default_set=True` → entry in `preferences.addons` **before** the import **[L]**.
5. Inside `quartz.session.restrict_blend()` and `quartz.registry.owner_scope(module_name)`: import;
   `pin_annotations(module)`; for an extension, deletes the module's `bl_info` and writes the one synthesized from the
   manifest **[L]**; `module.register()`.
6. Failure in any step → `handle_error(exc)` (default: traceback to `stderr`; a nonexistent module
   produces `ModuleNotFoundError` with `'Add-on not loaded: "<name>", cause: '` **[O]**); removes the
   module and its submodules from `sys.modules`; undoes `default_set`; returns `None` **[O]**. Classes
   registered before the failure stay registered (reportable leak) **[O]**.
7. Success → `module.__addon_enabled__ = True`, `module.__addon_persistent__ = persistent`,
   `module.__time__` (mtime) if absent; `dispatch("addon_enable_post", module_name)`; returns the
   module **[O]**.

`disable(module_name, *, default_set=False, refresh_handled=False, handle_error=None)`: if
enabled, `__addon_enabled__ = False` and `module.unregister()` under `owner_scope(module_name)`
(an error goes to `handle_error`, does not propagate) **[O]**; `default_set=True` → removes from
`preferences.addons`; the module **stays** in `sys.modules` **[O]**;
`dispatch("addon_disable_post", module_name)`.

`check(module_name)` → `(module_name in preferences.addons, module loaded and with
__addon_enabled__)`; `(False, False)` before, `(True, True)` after `enable(default_set=True)`,
`(False, False)` after `disable(default_set=True)` **[O]**.

#### 3.0.5 Sweep levels

Owner: `l3-cli-sweep` (§3.5.2); `AddonReport.reached` (§3.4.6) uses the same names.

| Level | Criterion for reaching it (cumulative) |
|---|---|
| `NONE` | — |
| `STATIC` | all `.py` files of the target parse with `ast`; the scan (§3.5.3) runs |
| `METADATA` | `bl_info` read and normalized, or valid manifest |
| `IMPORT` | import under RestrictBlend without an exception; for `SCRIPT`, execution as `__main__` to the end with exit 0 (maximum level for a script) |
| `REGISTER` | `register()` without an exception; counts of registered classes per base |
| `UI_SMOKE` | `quartz.ui.draw_ui` of each Panel/Menu/Header/UIList of the owner (respecting `poll`) and of the menus it extended, without `DRAW_EXCEPTION` |
| `UNREGISTER_CLEAN` | `unregister()` without an exception and empty `leaks(module)` (classes, props on types, menu functions, handlers) |

"Green" for a Blender corpus target = the same level as the Blender baseline
(`data/sweep/blender_baseline.json`) and the same class counts per base; the baseline measures
`UNREGISTER_CLEAN` by classes, handlers and dynamic props, and leaks of menu functions alone are not
part of the comparison (§3.5.5, `compare_baseline` in §3.5.2). The ratchet
(`data/sweep/ratchet.json`) keeps the best level per target and only goes up.

#### 3.0.6 Isolated execution (Rule 1)

1. Each sweep target runs in a subprocess `[sys.executable, "-I", "-B", "-X", "utf8", "-c", BOOT,
   *args]`, where `BOOT` inserts the project root into `sys.path` (`-I` does not insert it) and calls
   `quartz.cli.main(args)`; `cwd = <root>/tmp/sweep/cwd`; `QUARTZ_USER_DIR =
   <root>/tmp/sweep/user/<target>`; per-target timeout (default 60 s).
2. `-B` (no bytecode) and `sys.dont_write_bytecode = True`: importing from the Blender directory never
   writes there. The Blender corpus is read-only.
3. `--sweep-mode` (`settings.sweep_mode = True`): `socket.socket.connect` and
   `socket.create_connection` raise `PermissionError` in the process.
4. Nothing is written outside the project root; default outputs go to `data/sweep/` and `tmp/`.

#### 3.0.7 Tests in `tests/compat/` (owners per file, §0.4)

`test_activate.py`, `test_identity.py`, `test_types_view.py`, `test_props_filter.py`,
`test_app_shim.py`, `test_usage_surface.py` → `l3-compat-bpy`; `test_mathutils_shim.py`,
`test_bpy_extras_shim.py`, `test_gpu_blf_stubs.py` → `l3-compat-math-extras`;
`test_bmesh_shim.py` → `l3-bmesh`. The dump's `addon_lifecycle` probe is verified by `l3-addons`
(`tests/addons/`); the other probes, by `tests/contract/*.py` (`l3-compat-bpy`).

#### 3.0.8 L3 gate

1. `.venv/Scripts/python.exe -m pytest -q` passes in full from the root (L1–L3; `blender`, `sweep` and
   `corpus` skipped by default).
2. `tests/contract/*.py` (strict compat) reproduces the dump's probes and the judge's facts; the `addon_lifecycle` probe
   passes in `tests/addons/`.
3. `tests/sweep/test_fixture_sweep.py`: each fixture in §3.4.8 reaches the expected level, in-process and via subprocess.
4. The five CLI subcommands (`info`, `scan-addon`, `enable-addon`, `run-script`,
   `addon-sweep`) have green tests.
5. `tests/compat/test_usage_surface.py`: all Tier 1 symbols in `data/bpy_usage.json`
   resolve in the compat.
6. `tests/arch/test_compat_thin.py` green.
7. Outside the default gate (with `QUARTZ_RUN_SWEEP=1` and Blender installed): the corpus sweep writes
   `data/sweep/quartz_latest.json` and the ratchet does not regress.

### 3.1 `bpy` compat (`l3-compat-bpy`)

Delivers the activation of Path A (`quartz.compat`), the profile generated from the Blender 5.2.2 dump and the shims
`bpy`, `idprop`, `rna_prop_ui`, `bl_math`, `bl_ui` and `bl_operators`, plus `docs/COMPAT.md` and the contract
tests (`tests/contract/`). Uses only L1 and L2 (no L3 `quartz.*` module, not even inside functions;
importing sibling shims happens only in `classify_symbol`, rule 6, and in tests); the sibling tasks
consume this section through the names in §3.1.1–§3.1.6.

Exact inventory of files (the globs in §0.4 contain only these; `compat/__init__.py` MUST NOT exist,
because `compat/` is not a package):

```
quartz/compat/__init__.py  quartz/compat/profile.py  quartz/compat/blender_5_2.json  tools/gen_compat_profile.py
compat/bpy/__init__.py  compat/bpy/types.py  compat/bpy/props.py  compat/bpy/ops.py  compat/bpy/path.py  compat/bpy/msgbus.py
compat/bpy/utils/__init__.py  compat/bpy/utils/previews.py  compat/bpy/utils/units.py
compat/bpy/app/__init__.py  compat/bpy/app/handlers.py  compat/bpy/app/timers.py  compat/bpy/app/translations.py  compat/bpy/app/icons.py
compat/idprop/__init__.py  compat/idprop/types.py  compat/rna_prop_ui.py  compat/bl_math.py
compat/bl_ui/__init__.py  compat/bl_ui/utils.py  compat/bl_operators/__init__.py  compat/bl_operators/presets.py
docs/COMPAT.md  tests/compat/test_{activate,identity,types_view,props_filter,app_shim,usage_surface}.py
tests/contract/conftest.py  tests/contract/test_contract_*.py (list in §3.1.8)  tests/arch/test_compat_thin.py
```

Rules common to all shims of this task (§3.1.3–§3.1.6):

1. They import only stdlib, `quartz.*` and other shims; they MUST NOT import numpy (§0.5).
2. Re-exporting is by identity: `shim.X is quartz....X`. A shim contains only a re-export or a
   Blender quirk listed in this section (D1, §3.0.1); new logic goes to `quartz.compat`.
3. No import effect beyond importing their own submodules (§3.0.2); the profile is only read when an
   attribute needs it.
4. Public names of a shim = `{n for n, v in vars(mod).items() if not n.startswith("_") and not
   isinstance(v, types.ModuleType)}` (imported submodules do not count); they MUST be exactly those
   listed in the shim's block (names served only by the module's `__getattr__` are listed separately,
   as "dynamic"). Therefore every helper in the shim has a name starting with `_` (`import quartz.app
   as _app`, `from collections.abc import Callable as _Callable`), the shim MUST NOT use `from
   __future__ import annotations` (the name `annotations` would become public) and MUST NOT import a module
   without a `_` alias (same convention as §3.4.7), except the shim package's own submodules
   (`from . import <sub>`) listed in the shim's block, which stay bound under the public name (e.g.
   `bpy.types`, `bpy.app.handlers`; they do not count as public names, per the definition above). Every shim defines a module-level `__getattr__`: a name starting
   with `_` → `AttributeError` without recording (the import machinery queries `__path__`, `__spec__`…);
   other names → the `__getattr__` returned by `quartz.compat.shim_getattr("<dotted name of the
   module>")` (records and raises). `compat/bpy/__init__.py`, `types.py`, `ops.py`, `app/__init__.py`
   and `app/translations.py` have their own `__getattr__` (below), which for unhandled names falls back to
   that same rule.
5. Interaction with L1/L2 only through the names in §0/§1 and §2: `quartz.app.settings.settings`,
   `quartz.app.paths.compat_dir/user_dir`, `quartz.rna.hooks.install/snapshot`, `quartz.registry`
   (§2.5.1), `quartz.ui.placeholder_type` (§2.5.6), `quartz.types.__dir__/__getattr__` (§2.2.1),
   `quartz.types.id.ID/id_type_info` (§2.2.4), `quartz.types.blenddata.BlendData/IMPLEMENTED/
   IDCollection` (§2.2.5), `quartz.types.ui.Menu` (§2.5.3), `quartz.contexts.Context/
   CONTEXT_MEMBERS/CONTEXT_METHODS/providers` (§2.6.2), `quartz.session.api_data/api_context/current/
   restrict_blend` (§2.6.1), `quartz.ops.submodule/submodule_names` (§2.6.3),
   `quartz.math.bvhtree.set_object_adapter/set_bmesh_adapter` (§1.4.9),
   `quartz.types.mesh.set_editmode_hooks` (§2.3.1), `quartz.props`, `quartz.rna`, `quartz.utils`
   (§2.5.7–§2.5.9), `quartz.path`, `quartz.app.*`, `quartz.math.scalar`, `quartz.errors`.

#### 3.1.1 `quartz/compat/__init__.py`

```python
SHIM_MODULES: frozenset[str] = frozenset({"bpy", "mathutils", "bmesh", "bpy_extras", "addon_utils", "idprop", "rna_prop_ui",
                                          "bl_math", "bl_ui", "bl_operators", "gpu", "gpu_extras", "blf", "aud"})
COMPAT_OWNER: str = "quartz.compat"
SYMBOL_CLASSES: tuple[str, ...] = ("IMPLEMENTED", "PHANTOM", "MISSING")
UI_NAME_RE: re.Pattern[str]      # the SAME object as quartz.compat.profile.UI_NAME_RE (§3.1.2); group 1 = kind
TYPE_ALIASES: Mapping[str, str] = {   # name in bpy.types -> dotted path of the object (resolved lazily)
    "bpy_struct": "quartz.rna.Struct", "bpy_prop_collection": "quartz.rna.PropCollection", "bpy_prop_array": "quartz.rna.PropArray",
    "Struct": "quartz.rna.RNAStruct", "Property": "quartz.rna.RNAProperty", "EnumPropertyItem": "quartz.rna.RNAEnumItem",
    "Context": "quartz.contexts.Context"}
CONTEXT_IMPLEMENTED: frozenset[str] = frozenset({   # members with a real provider in §2.6.2 (29) + CONTEXT_METHODS (4)
    "window_manager", "window", "screen", "workspace", "scene", "view_layer", "blend_data", "preferences", "tool_settings",
    "engine", "layer_collection", "collection", "active_object", "object", "mode", "edit_object", "selected_objects",
    "selected_editable_objects", "visible_objects", "editable_objects", "selectable_objects", "objects_in_mode",
    "objects_in_mode_unique_data", "sculpt_object", "vertex_paint_object", "weight_paint_object", "image_paint_object",
    "particle_edit_object", "pose_object", "copy", "evaluated_depsgraph_get", "path_resolve", "temp_override"})
def activate(*, strict: bool = False, blender_version: tuple[int, int, int] | None = None) -> None
def deactivate() -> None
def is_active() -> bool                          # _active is not None
def is_strict() -> bool                          # is_active() and not settings.lenient_ui
@contextmanager
def activated(*, strict: bool = False) -> Iterator[None]
def note_missing(symbol: str) -> None            # Counter += 1; no-op if settings.record_missing is False
def missing_symbols() -> "collections.Counter[str]"   # COPY of the counter
def clear_missing() -> None
def profile() -> "CompatProfile"                 # load_profile() on the 1st call; afterwards always the same object
def classify_symbol(dotted: str) -> str          # one of SYMBOL_CLASSES; never records
def resolve_type(name: str) -> type | None       # resolver for names missing from the registry (installed by activate)
def type_alias(name: str) -> object | None       # importlib + getattr of the path in TYPE_ALIASES[name]; None if not an alias
def bpy_types_getattr(name: str) -> object       # body of compat/bpy/types.__getattr__
def bpy_types_dir() -> list[str]                 # body of compat/bpy/types.__dir__
def shim_getattr(module: str) -> Callable[[str], NoReturn]   # factory for the shims' module-level __getattr__
```

`import quartz.compat` has no side effect (it does not import session, registry or shims; it MAY import
`quartz.compat.profile`, which also has none). Internal state: `_active: dict | None` (values
saved in step 3 of §3.0.3 and the `sys.path` entry from step 4), `_missing: Counter`,
`_phantoms: dict[str, type]`, `_placeholders: set[str]`, `_profile: CompatProfile | None`.

**Activation**: `activate` follows §3.0.3, with these additions:

1. Before step 1: `blender_version` not `None` and `tuple(blender_version)` different from
   `profile().blender_version` → `CompatError` with `"unsupported Blender version"` (applies also
   when already active; nothing changes).
2. Step 1: the `"bpy"` in `sys.modules` is "from the compat" if `Path(mod.__file__).resolve()
   .is_relative_to(compat_dir().resolve())`; a module without `__file__` (or `None`) counts as foreign →
   `CompatError` with `"already loaded"`.
3. Step 3 saves `settings.api_prefix`, `settings.lenient_ui`, `settings.record_missing` and
   `hooks.snapshot()["note_missing"]`/`["repr_root"]`. Step 4 saves `entry = str(compat_dir())`
   (the value used in the insertion, even if it was already in `sys.path`); `deactivate` uses this saved
   value and never rereads `compat_dir()` (the env may have changed). It also saves in `_active`, before
   step 4, `pre = {n for n in ("mathutils", "bmesh", "quartz.extras", "quartz.bmesh") if n in
   sys.modules}` (only reads `sys.modules`; imports nothing).
4. Step 8 failing: undoes 4–7 (including the settings from step 5), removes from `sys.modules` the names
   with a top-level component in `SHIM_MODULES` inserted by the attempt, leaves `is_active()` false and re-raises the
   original exception.
5. `activate` does NOT clear the missing-symbols log and does not create a session.

**Deactivation**: `deactivate()`, idempotent (inactive → returns), executes all steps even if
an earlier one raises, and re-raises the first exception at the end. Before step 1 it computes, with `pre =
_active["pre"]`: `clean_obj = "mathutils" in sys.modules and "mathutils" not in pre and
"quartz.extras" not in pre` and `clean_bm = "bmesh" in sys.modules and "bmesh" not in pre and
"quartz.bmesh" not in pre` (the shim was imported during this activation and nobody could have called the owner's
`install_adapters()` before it):

1. `registry.unregister_class(c)` for each `c` in `registry.classes_owned_by(COMPAT_OWNER)` that
   is still registered, in reverse order; empties `_phantoms` and `_placeholders`.
2. `registry.set_missing_type_resolver(None)`.
3. `hooks.install(note_missing=<saved>, repr_root=<saved>)`; restores the three saved settings.
4. Removes all occurrences of the saved `entry` from `sys.path`; removes from `sys.modules` every name
   whose first component (`name.split(".")[0]`) is in `SHIM_MODULES`.
5. Adapters back to the default (§3.0.2), only those installed by a shim imported during this activation:
   `clean_obj` → `quartz.math.bvhtree.set_object_adapter(None)`; `clean_bm` →
   `quartz.math.bvhtree.set_bmesh_adapter(None)` and, if `importlib.util.find_spec("quartz.types.mesh")`
   is not `None`, `quartz.types.mesh.set_editmode_hooks()`. Adapters that may have been
   installed before the activation (by `quartz.cli.main`, §3.5.1 step 5, which imports
   `quartz.extras`/`quartz.bmesh`, or by an explicit call to `install_adapters()`) are left
   intact; this way `classify_symbol`/`scan.predict` with the compat inactive do not undo the adapters
   of whoever installed them. Exiting `quartz.testing.isolated()` still returns all of them to the default
   (§2.6.8).
6. `_active = None`. The missing-symbols log is kept (only `clear_missing()` zeroes it).

`activated(strict)`: saves `was = is_active()` and `prev = is_strict()`; `activate(strict=strict)`;
`yield`; on exit (always): `deactivate()` if `not was`, otherwise `activate(strict=prev)`.

**Resolver**: `resolve_type(name)` (consulted by `registry.lookup(name)` when `name` is not
registered):

1. `name` not an identifier (`str.isidentifier`) or starting with `_` → `None`.
2. `name in TYPE_ALIASES` or `name in quartz.types.__dir__()` → `None`. An implemented type is never
   shadowed by a phantom, and the resolver MUST NOT return built-in types that are not registered (§2.5.1:
   `lookup` returns only registered ones or what the resolver created; whoever wants the catalog uses the
   `bpy.types` view or `quartz.types`).
3. `name in _phantoms` → the stored phantom.
4. `kind = profile().ui_types.get(name)`; if `None`, `settings.lenient_ui` and `UI_NAME_RE` matches →
   `kind` = group 1. With `kind`: `cls = quartz.ui.placeholder_type(name, kind, owner=COMPAT_OWNER)`
   (which already registers under the owner when needed and always returns the same class, §2.5.6); if `name not
   in _placeholders` (internal `set[str]`) → adds it and `note_missing(f"bpy.types.{name}")`;
   returns `cls`. `ValueError` from `placeholder_type` (name outside its rule, or cached name
   with a different `kind`) → proceeds to step 5 **[I]**. `_placeholders` is emptied by `deactivate` (step 1).
5. `name in profile().type_names` → creates the **inert phantom type**:
   `builtin_struct(type(name, (base,), {"__module__": "bpy.types", "_q_phantom": True}), identifier=name)`
   with `base = quartz.types.id.ID` if `name in profile().id_type_names`, otherwise `quartz.rna.Struct`
   **[I]**; stores it in `_phantoms`; `note_missing(f"bpy.types.{name}")`; returns it. The phantom has no
   RNA props, accepts dynamic extension (`bpy.types.Bone.x = bpy.props.IntProperty()` and `del
   bpy.types.Bone.x`) and, as a subclass of `ID`, makes `PointerProperty(type=bpy.types.Action)` default to
   `None`.
6. Otherwise `None`.

Recording happens only on the 1st resolution of each name per activation (`_placeholders`/`_phantoms`,
emptied by `deactivate`); later accesses do not record. Placeholders stay in the registry under
`COMPAT_OWNER` (ignored by `counts_by_base` and by the leak reports, which skip owners
`"quartz.*"`, §2.5.1); phantoms belong to the compat but are not registered (they have no
registrable base): `registry.lookup` returns them only through the resolver.

**`bpy.types` view**: `bpy_types_getattr(name)`: (1) `_`-prefixed → `AttributeError`; (2)
`type_alias(name)`; (3) `name in quartz.types.__dir__()` → `getattr(quartz.types, name)` (never a module
name such as `install_hooks`); (4) `obj = quartz.registry.lookup(name)` (with resolver: registered ones,
then `resolve_type`); (5) nothing → `note_missing(f"bpy.types.{name}")` and
`AttributeError(f"module 'bpy.types' has no attribute '{name}'")`. Nothing is stored in the module (registration
and unregistration take effect immediately). Strict vs. lenient comes only from step 4 of `resolve_type` (§3.0.3). The
implementation MAY cache `frozenset(quartz.types.__dir__())` after the 1st query (the catalog does not
change after `load_builtin_types`), but MUST NOT cache results of `lookup`.
`bpy_types_dir()` = `sorted(TYPE_ALIASES ∪ quartz.types.__dir__() ∪ {registry.rna_name_of(c) for c in
registry.iter_classes()} ∪ profile().type_names)`.

**Missing-symbols log**: `note_missing` is also the `note_missing` hook of `quartz.rna.hooks` while
active (§2.1.1), so it receives `"bpy.data.<phantom collection>"`, `"bpy.ops.<mod>.<op>"`,
`"bpy.types.UILayout.<fn>"`, `"bpy.context.asset_library_reference"` coming from L2. `shim_getattr(m)`
returns `f(name)` that records `f"{m}.{name}"` and raises `AttributeError(f"module '{m}' has no attribute
'{name}'")` (for `_`-prefixed names, it raises without recording).

**Classification**: `classify_symbol(dotted)`, in this order: (a) first component outside
`SHIM_MODULES` → `ValueError` with `"not a compat symbol"` (before activating anything); (b) if
inactive, enters `activated(strict=True)` (a foreign `bpy` in `sys.modules` propagates the
`CompatError`); (c) saves `settings.record_missing` and sets it to `False`; (d) applies the rules
below; (e) on exit (always) restores `record_missing` and leaves `activated`. Never creates
placeholders/phantoms and never records. MAY call `quartz.session.current()` (rule 5), which creates the
session if it does not yet exist.

1. Exactly `bpy`, `bpy.types`, `bpy.data` or `bpy.context` → IMPLEMENTED.
2. `bpy.types.N[.rest]`: N an alias, in the `quartz.types` catalog or registered with owner ≠ `COMPAT_OWNER`
   (`registry.lookup(N, resolve=False)`) → IMPLEMENTED if each component of `rest` exists via
   chained `hasattr` on the class, otherwise MISSING; N registered under `COMPAT_OWNER`, in `_phantoms`, in
   `profile().type_names`, or (`is_active()` lenient and `UI_NAME_RE` matches) → PHANTOM; otherwise MISSING.
3. `bpy.data.N[.rest]`: `N in quartz.types.blenddata.IMPLEMENTED` → class = `id_type_info(N).collection_cls`
   or `IDCollection`; IMPLEMENTED if `rest` exists via `hasattr` on it, otherwise MISSING; `N ==
   "all_ids"` (implemented view of all IDs, §2.2.5) → IMPLEMENTED **[I]**; `N` in
   `profile().data_collections` (not implemented) → PHANTOM; `hasattr(BlendData, N)` (e.g.
   `filepath`, `is_dirty`, `orphans_purge`) → IMPLEMENTED; otherwise MISSING.
4. `bpy.context.N[.rest]`: `N in CONTEXT_IMPLEMENTED` or `N in quartz.contexts.providers()` with
   `N not in profile().context_members` (native provider) → IMPLEMENTED (without looking at `rest`) **[I]**;
   `N in profile().context_members` → PHANTOM; otherwise MISSING.
5. `bpy.ops` → IMPLEMENTED; `bpy.ops.M` → IMPLEMENTED if `M in quartz.ops.submodule_names()` (after
   `quartz.session.current()`, which registers the built-ins), otherwise MISSING; `bpy.ops.M.O[.x]` → IMPLEMENTED if
   `registry.operator_class(f"{M}.{O}")` exists and `x` (if any) ∈ `{"poll", "idname", "idname_py",
   "get_rna_type", "bl_options"}`; otherwise MISSING (even if it exists in Blender: the call would fail).
6. The rest (`bpy.app…`, `bpy.utils…`, `bpy.props…`, `bpy.path…`, `bpy.msgbus…`, `mathutils…`,
   `gpu…`, `idprop…`…): `importlib.import_module(<top>)` (`ImportError` from the top-level shim itself,
   e.g. a sibling that does not exist yet → MISSING) and walks the components with `getattr`; a missing attribute →
   tries `importlib.import_module` of the dotted prefix up to that point (submodule); `ImportError` or
   `AttributeError` → MISSING; found → PHANTOM if `getattr(obj, "_q_phantom", False) is True`, otherwise
   IMPLEMENTED. Shims and modules of other tasks MUST mark with `_q_phantom = True` every
   NI surface they serve (list in §3.2, rule 2, and §3.3, rule 5); those of this task do too
   (icons, §3.1.5). Objects re-exported from L1 by identity (e.g. the NI ones in `quartz.math.noise`,
   §1.4.9) are not marked (no L3 task mutates L1 objects) and classify as IMPLEMENTED.

Errors: `CompatError` (`"already loaded"`, `"unsupported Blender version"`); `ValueError` (`"not a compat
symbol"`); `AttributeError` (`"module 'bpy.types' has no attribute '"`, `f"module '{m}' has no
attribute '{name}'"`).

#### 3.1.2 `quartz/compat/profile.py`, `quartz/compat/blender_5_2.json`, `tools/gen_compat_profile.py`

```python
PROFILE_FORMAT: str = "quartz.compat.profile"
PROFILE_FORMAT_VERSION: int = 1
PROFILE_PATH: Path = Path(__file__).with_name("blender_5_2.json")
UI_NAME_RE: re.Pattern[str] = re.compile(r"^[A-Z][A-Z0-9_]*_(MT|PT|HT|UL)_[A-Za-z0-9_]+$")   # group 1 = kind
    # matches exactly the 1977 names in dump["types_names"] that contain _MT_/_PT_/_HT_/_UL_ [O]
@dataclass(frozen=True)
class CompatProfile:
    blender_version: tuple[int, int, int]           # (5, 2, 2) [O]
    version_file: tuple[int, int, int]              # (5, 2, 45) [O]
    version_string: str                             # "5.2.2 LTS" [O]
    version_cycle: str                              # "release" [O]
    handler_names: tuple[str, ...]                  # 39, dump order (app.handler_lists) [O]
    context_members: tuple[str, ...]                # 71, alphabetical order, without the 4 methods [O]
    data_collections: Mapping[str, str]             # 40, dump order: attribute -> RNA struct ("" when the dump gives null) [O]
    type_names: frozenset[str]                      # 4023 [O]
    ui_types: Mapping[str, str]                     # names in type_names that match UI_NAME_RE -> "MT"|"PT"|"HT"|"UL" (685/1233/26/33) [O]
    props_kwargs: Mapping[str, tuple[str, ...]]     # 11 entries of dump["props"] (without "__deferred__") -> kwargs in order [O]
    uilayout_functions: Mapping[str, tuple[str, ...]]   # 116 [O]
    class_enums: Mapping[str, tuple[str, ...]]      # 19: f"{base}.{prop}" for ENUM "bl_*" props of base_classes [O]
    operator_names: frozenset[str]                  # 2499 idname_py f"{mod}.{op}" of ops.submodules [O]
    app: Mapping[str, object]                       # {"attributes": {...}, "timers": [...], "translations": [...], "icons": [...]}
    id_type_names: frozenset[str]                   # required (no default); 45: keys of id_types ∪ fixed_type of data.collections, minus "ID" [O]
def load_profile(path: str | Path | None = None) -> CompatProfile    # None -> PROFILE_PATH; = profile_from_dict(json.load(...))
def profile_from_dict(data: Mapping[str, object]) -> CompatProfile   # validates and converts a document (without reading a file)
def generate_profile(dump: Mapping[str, object]) -> dict             # pure: dump -> profile JSON document
def profile_to_text(data: Mapping[str, object]) -> str               # canonical serialization (byte-for-byte reproducible)
# tools/gen_compat_profile.py
DEFAULT_DUMP: Path   # <root>/data/blender_api_dump.json
DEFAULT_OUT: Path    # <root>/quartz/compat/blender_5_2.json
def main(argv: Sequence[str] | None = None) -> int
```

Document (`generate_profile`): `{"format": PROFILE_FORMAT, "format_version": 1, "author": "D1on1n",
"blender_version", "version_file", "version_string"` (from `dump["meta"]`), `"version_cycle"`
(`dump["app"]["attributes"]["version_cycle"]["value"]`), `"handler_names"` (`dump["app"]["handler_lists"]`,
in order), `"context_members"` (`sorted` keys of `dump["context"]` whose value does not have
`"kind": "method"`), `"data_collections"` (list of `[attribute, struct or ""]` pairs from
`dump["data"]["collections"]`, preserving order), `"type_names"` (`sorted(dump["types_names"])`),
`"ui_types"` (`{n: UI_NAME_RE.match(n).group(1)}` for each `n` in `type_names` that matches),
`"props_kwargs"` (`{f: dump["props"][f]["kwargs"]}`, without `"__deferred__"`), `"uilayout_functions"`
(`dump["extras"]["UILayout_functions"]`), `"class_enums"` (`{f"{base}.{prop}": spec["items"]}` for
each `prop` in `dump["base_classes"][base]["properties"]` that starts with `"bl_"` and has `"type":
"ENUM"`), `"operator_names"` (`sorted(f"{mod}.{op}")` from `dump["ops"]["submodules"]`),
`"id_type_names"` (`sorted` of the keys of `dump["id_types"]` ∪ non-null `fixed_type` of
`dump["data"]["collections"]`, minus `"ID"`), `"app"}`. `app.attributes` =
for each attribute of `dump["app"]["attributes"]`, `{"type": t}` plus `"value"` only if `t ∈ {"bool",
"int", "str", "tuple"}` and the name ∉ `{"binary_path", "tempdir", "cachedir"}` (machine paths);
`app.timers/translations/icons` = the lists from the dump. No timestamp; only names, kwargs, enums
and simple values (clean-room, D17). `generate_profile` reads neither files nor the clock.

`profile_to_text(d)` = `json.dumps(d, ensure_ascii=True, indent=1, sort_keys=True) + "\n"`; the file is
written in UTF-8 with `newline="\n"`. `load_profile`: reads the JSON (UTF-8) and calls `profile_from_dict`;
invalid JSON → `CompatError` with `"invalid compat profile"`; missing file →
`FileNotFoundError`. `profile_from_dict`: `format` ≠ `PROFILE_FORMAT`, `format_version` ≠
`PROFILE_FORMAT_VERSION` or a missing `CompatProfile` field (all fields, including
`id_type_names`, are required in the document) → `CompatError` with `"invalid compat
profile"` (extra keys, such as `"author"`, are ignored); converts `blender_version`/`version_file`
and each list of ordered names into `tuple`, `type_names`/`operator_names`/`id_type_names` into
`frozenset`, `data_collections` into `MappingProxyType(dict(pairs))` (pair order), other
dictionaries into `MappingProxyType` with list values → `tuple`; `app` is converted in depth
(dict → `MappingProxyType`, list → `tuple`). Two profiles with the same data are `==`.
`blender_5_2.json` MUST be exactly `profile_to_text(generate_profile(<current dump>))`.

`tools/gen_compat_profile.py` (`main`, `if __name__ == "__main__": raise SystemExit(main())`): inserts the
project root (`Path(__file__).resolve().parents[1]`) into `sys.path` before importing `quartz`;
options `--dump PATH` (default `DEFAULT_DUMP`), `--out PATH` (default `DEFAULT_OUT`), `--check`. Order:
(1) `--out` whose `Path(out).resolve()` is not `is_relative_to(<root>)` → prints `"refusing to write
outside the project"` to `stderr` and returns 2 (§0.1(5)), with or without `--check`, before reading the dump;
(2) missing dump or invalid JSON → message with `"cannot read dump"` to `stderr` and 2; (3) without
`--check`: writes the text (creates the parent directory if needed) and returns 0; `--check`: does not write;
returns 0 if the file exists and its bytes are identical to those of the text in UTF-8, otherwise prints
`"profile out of date"` to `stderr` and returns 1. Argument error → 2 (argparse). Nothing is printed
to `stdout` other than an optional summary line.

Errors: `CompatError` with `"invalid compat profile"`; `FileNotFoundError` (missing profile).

#### 3.1.3 `compat/bpy/__init__.py` and `compat/bpy/types.py`

```python
# compat/bpy/__init__.py
from . import types, props, ops, utils, path, app, msgbus          # submodules (files in compat/bpy)
def __getattr__(name: str) -> object
    # "data" -> quartz.session.api_data(); "context" -> quartz.session.api_context()  (ON EACH access; never stored)
    # leading "_" -> AttributeError; others -> quartz.compat.note_missing(f"bpy.{name}") + AttributeError(f"module 'bpy' has no attribute '{name}'")
def __dir__() -> list[str]          # ["app", "context", "data", "msgbus", "ops", "path", "props", "types", "utils"]
# compat/bpy/types.py
def __getattr__(name: str) -> object  # = quartz.compat.bpy_types_getattr(name)
def __dir__() -> list[str]            # = quartz.compat.bpy_types_dir()
```

1. `import bpy` leaves in `sys.modules` `bpy`, `bpy.types`, `bpy.props`, `bpy.ops`, `bpy.utils`,
   `bpy.utils.previews`, `bpy.utils.units`, `bpy.path`, `bpy.app`, `bpy.app.handlers`, `bpy.app.timers`,
   `bpy.app.translations`, `bpy.app.icons`, `bpy.msgbus` (real files; `from bpy.types import Panel`
   and `import bpy.app.handlers` work). Public names of `compat/bpy/__init__.py`: none besides
   the submodules; dynamic: `data`, `context`.
2. `from bpy import data` captured before `quartz.session.reset()` remains the same object
   afterwards (D14); inside `quartz.session.restrict_blend(enabled=True)`, `bpy.data`/`bpy.context`
   return `RestrictedData`/`RestrictedContext` (§2.1.7).
3. Identity: `bpy.types.Object is quartz.types.Object` (every name in the catalog); documented
   exceptions: `bpy.types.Struct is quartz.rna.RNAStruct` and `bpy.types.Property is
   quartz.rna.RNAProperty` (not `quartz.rna.Struct`); `bpy.types.bpy_struct is quartz.rna.Struct`.
4. `bpy.types` does not store attributes in the module: a registered class appears by its RNA name on the spot
   (`MOD_OT_name` **[O]**) and disappears when unregistered.

Errors: `AttributeError` with `"module 'bpy' has no attribute '"` / `"module 'bpy.types' has no attribute
'"`, always annotated.

#### 3.1.4 `compat/bpy/props.py`, `compat/bpy/ops.py`, `compat/bpy/path.py`, `compat/bpy/msgbus.py`, `compat/bpy/utils/**`

```python
# compat/bpy/props.py — the 10 recreated factories + 2 re-exports (11 names from dump["props"] + _PropertyDeferred)
def BoolProperty(*args, **kwargs) -> _PropertyDeferred     # make_deferred(BoolProperty, "BOOLEAN", args, kwargs, allow_meta=False)
def BoolVectorProperty(*args, **kwargs) -> _PropertyDeferred   # "BOOLEAN_VECTOR"
def IntProperty(*args, **kwargs) -> _PropertyDeferred      # "INT"
def IntVectorProperty(*args, **kwargs) -> _PropertyDeferred    # "INT_VECTOR"
def FloatProperty(*args, **kwargs) -> _PropertyDeferred    # "FLOAT"
def FloatVectorProperty(*args, **kwargs) -> _PropertyDeferred  # "FLOAT_VECTOR"
def StringProperty(*args, **kwargs) -> _PropertyDeferred   # "STRING"
def EnumProperty(*args, **kwargs) -> _PropertyDeferred     # "ENUM"; items required
def PointerProperty(*args, **kwargs) -> _PropertyDeferred  # "POINTER"; type required
def CollectionProperty(*args, **kwargs) -> _PropertyDeferred   # "COLLECTION"; type required
RemoveProperty = quartz.props.RemoveProperty               # same object
_PropertyDeferred = quartz.props._PropertyDeferred         # same object
# compat/bpy/ops.py
def __getattr__(name: str) -> "OpsSubmodule"   # leading "_" -> AttributeError; otherwise quartz.ops.submodule(name) (not annotated: the absence shows up at the call)
def __dir__() -> list[str]                     # quartz.ops.submodule_names()
# compat/bpy/path.py — the 17 names from dump["path"], same objects as quartz.path
# compat/bpy/msgbus.py — subscribe_rna, publish_rna, clear_by_owner (same as quartz.app.msgbus; WITHOUT flush)
# compat/bpy/utils/__init__.py — the 44 function names from dump["utils"] (same as quartz.utils) + submodules previews, units
# compat/bpy/utils/previews.py — new, remove, ImagePreviewCollection (same as quartz.utils.previews)
# compat/bpy/utils/units.py — categories, systems, to_string, to_value (same as quartz.utils.units)
```

1. Each `bpy.props` factory is a function of the shim itself (`__module__ == "bpy.props"`, `__name__` =
   factory name) and calls `quartz.props.make_deferred(<itself>, kind, args, kwargs,
   allow_meta=False)`; therefore `IntProperty(name="x", default=3).function is bpy.props.IntProperty` and
   `keywords == {"name": "x", "default": 3}` **[O]**, and `bpy.props.IntProperty is not
   quartz.props.IntProperty`. `meta=` → `TypeError` with `"unexpected keyword argument 'meta'"` (D4).
   The requirement for `items`/`type` and the positional rules are identical to those of the `quartz.props` factory
   (`TypeError`; the message cites the argument name or the factory).
2. The `bpy.props` deferred objects install properties exactly like those of `quartz.props` (annotation,
   `bpy.types.Scene.x = …`, `PropertyGroup`).
3. `bpy.ops.mesh is quartz.ops.mesh`; operator error messages cite `bpy.ops` because
   `settings.api_prefix == "bpy"` with compat active (§2.1.8).
4. `bpy.utils.previews` and `bpy.utils.units` are the shim modules (whose members are those of
   `quartz.utils.previews/units`); `bpy.utils.register_class is quartz.registry.register_class`.
   `compat/bpy/utils/__init__.py` imports both submodules (`from . import previews, units`).
5. `bpy.ops` has no static public names; `bpy.ops.<mod>` is always the `OpsSubmodule` from
   `quartz.ops.submodule(mod)` (same instance on each access), including for submodules without a
   registered operator (the absence shows up only at the call **[O]**).

Errors: `TypeError` with `"unexpected keyword argument 'meta'"` (`bpy.props` factories, coming from
`make_deferred`, §1.6.1); `AttributeError` for a leading-`_` name in `bpy.ops` (not annotated) and the one from
`quartz.ops.submodule` for a non-identifier name; `AttributeError` annotated with `"module
'bpy.utils' has no attribute '"` (likewise `bpy.path`, `bpy.msgbus`, `bpy.props`, `bpy.utils.previews`,
`bpy.utils.units`).

#### 3.1.5 `compat/bpy/app/**`

```python
# compat/bpy/app/__init__.py
from . import handlers, timers, translations, icons        # submodules
def __getattr__(name: str) -> object
    # "version"/"version_file"/"version_string"/"version_cycle" -> field of quartz.compat.profile() ((5,2,2), (5,2,45), "5.2.2 LTS", "release") [O]
    # _FORWARDED -> getattr(quartz.app, name) on each access; other missing names -> shim_getattr("bpy.app")
_FORWARDED: tuple[str, ...] = ("background", "factory_startup", "debug", "debug_value", "binary_path", "driver_namespace",
                              "online_access", "online_access_override", "portable", "python_args", "tempdir", "cachedir")
alembic, ocio, oiio, opensubdiv, openvdb, sdl, usd   # _LibInfo(supported=False, version=(0, 0, 0), version_string="Unknown") [O shape of sdl]
ffmpeg            # _FFmpegInfo(supported=False, avcodec_version=(0,0,0), avcodec_version_string="Unknown", … avdevice/avformat/avutil/swscale) [I names]
build_branch = b"quartz"; build_hash = b"unknown"; build_type = b"Release"; build_system = b"Quartz"
build_platform: bytes     # platform.system().encode()
build_date = build_time = build_commit_date = build_commit_time = b""   # no clock (§0.2)
build_cflags = build_cxxflags = build_linkflags = b""; build_commit_timestamp = 0
build_options             # _BuildOptions(): every public attribute -> False [I]
autoexec_fail = False; autoexec_fail_message = ""; autoexec_fail_quiet = False; module = False      # [O]
debug_depsgraph = debug_depsgraph_build = debug_depsgraph_eval = debug_depsgraph_pretty = debug_depsgraph_tag = False
debug_depsgraph_time = debug_events = debug_freestyle = debug_handlers = debug_io = debug_python = debug_simdata = debug_wm = False   # [O]
render_icon_size = 32; render_preview_size = 128; use_event_simulate = False; use_userpref_skip_save_on_exit = True   # [O]
def is_job_running(job_type: str) -> bool        # False
def memory_usage_undo() -> int                   # 0
def help_text(*, all: bool = False) -> str       # "" [I]
# compat/bpy/app/handlers.py — for each name in quartz.app.handlers.BLENDER_HANDLER_NAMES (39): the SAME list; + persistent (same object)
# compat/bpy/app/timers.py — register, unregister, is_registered (same as quartz.app.timers)
# compat/bpy/app/translations.py — contexts, contexts_C_to_py, locale_explode, pgettext, pgettext_data, pgettext_iface, pgettext_n,
#   pgettext_rpt, pgettext_tip, register, unregister (same objects); locale and locales via __getattr__ (read from quartz.app.translations on each access)
# compat/bpy/app/icons.py
def new_triangles(range: tuple[int, int], coords: bytes, colors: bytes) -> NoReturn     # NotImplementedInQuartz("bpy.app.icons.new_triangles")
def new_triangles_from_file(filepath: str) -> NoReturn                               # NotImplementedInQuartz("bpy.app.icons.new_triangles_from_file")
def release(icon_id: int) -> NoReturn                                                # NotImplementedInQuartz("bpy.app.icons.release")
```

1. The support classes (`_LibInfo`, `_FFmpegInfo`, `_BuildOptions`) and `_FORWARDED` are private (`_`);
   `_LibInfo`/`_FFmpegInfo` MAY be `collections.namedtuple` (indexable like Blender's
   *struct sequence*; `bpy.app.sdl` in the dump is `[false, [0, 0, 0], "Unknown"]` **[O]**). `bpy.app` itself
   is a module and does not expose *struct sequence* artifacts (`n_fields`, `n_sequence_fields`,
   `n_unnamed_fields`, `count`, `index`): documented divergence.
2. `bpy.app.handlers` exposes only the 39 Blender names and `persistent`: `bpy.app.handlers.startup_post`
   → annotated `AttributeError`; `bpy.app.handlers.load_post is quartz.app.handlers.load_post` (the list
   survives `handlers.restore`, which is in place).
3. The three `icons` functions have `_q_phantom = True` (classified PHANTOM, §3.1.1) and, when
   called, run `quartz.compat.note_missing(<symbol>)` before raising (same NI rule as
   §3.2).
4. Public names of `compat/bpy/app/__init__.py` (rule 4): the libs, `ffmpeg`, the `build_*` names,
   `build_options`, `autoexec_fail*`, `module`, the listed `debug_depsgraph*`/`debug_*` names,
   `render_icon_size`, `render_preview_size`, `use_event_simulate`, `use_userpref_skip_save_on_exit`,
   `is_job_running`, `memory_usage_undo`, `help_text`; dynamic: `version`, `version_file`,
   `version_string`, `version_cycle` and those in `_FORWARDED`. `compat/bpy/app/translations.py`:
   the 11 listed names; dynamic `locale`, `locales`. `compat/bpy/app/handlers.py`: the 39 names
   and `persistent`.
5. `bpy.app.version` etc. read the profile on the 1st lookup (§3.0.2), never at shim import.

Errors: `NotImplementedInQuartz` with `"bpy.app.icons.new_triangles is not implemented in Quartz"`;
`AttributeError` with `"module 'bpy.app' has no attribute '"`.

#### 3.1.6 `compat/idprop/**`, `compat/rna_prop_ui.py`, `compat/bl_math.py`, `compat/bl_ui/**`, `compat/bl_operators/**`

```python
# compat/idprop/__init__.py: from . import types        compat/idprop/types.py: IDPropertyGroup, IDPropertyArray (= quartz.rna)
# compat/rna_prop_ui.py: rna_idprop_ui_create, rna_idprop_value_to_python, rna_idprop_quote_path (= quartz.rna)
# compat/bl_math.py: clamp, lerp, smoothstep (= quartz.math.scalar)
# compat/bl_ui/__init__.py: from . import utils           compat/bl_operators/__init__.py: from . import presets
# compat/bl_ui/utils.py
class PresetPanel:                                  # original mixin for subclasses of bpy.types.Panel
    bl_space_type: str = "PROPERTIES"; bl_region_type: str = "HEADER"; bl_label: str = "Presets"   # [I]
    path_menu = vars(quartz.types.Menu)["path_menu"]   # the same object as Menu.path_menu (§2.5.3)
    @classmethod
    def draw_panel_header(cls, layout) -> None      # layout.popover(panel=cls.__name__, icon="PRESET", text="")
    @classmethod
    def draw_menu(cls, layout, text: str | None = None) -> None   # layout.popover(panel=cls.__name__, icon="PRESET", text=text or cls.bl_label)
    def draw(self, context) -> None                 # self.layout.emboss = "NONE"; operator_context = "EXEC_DEFAULT"; quartz.types.Menu.draw_preset(self, context)
# compat/bl_operators/presets.py
class AddPresetBase:                                # original mixin for subclasses of bpy.types.Operator
    bl_options: set[str] = {"REGISTER", "INTERNAL"}
    name: _bpy.props.StringProperty(name="Name", maxlen=64, options={"SKIP_SAVE"})
    remove_name: _bpy.props.BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})
    remove_active: _bpy.props.BoolProperty(default=False, options={"HIDDEN", "SKIP_SAVE"})
    @staticmethod
    def as_filename(name: str) -> str               # quartz.path.clean_name(name.strip()) [I]
    def check(self, context) -> bool                # False
    def invoke(self, context, event) -> set[str]    # remove_active -> execute; otherwise context.window_manager.invoke_props_dialog(self)
    def execute(self, context) -> set[str]
```

1. `AddPresetBase.execute`, in this order: (a) `dir = quartz.utils.user_resource("SCRIPTS",
   path=f"presets/{self.preset_subdir}", create=False)` (nothing is created yet); (b) `target = (Path(dir)
   / (as_filename(self.name) + ".py")).resolve()`; (c) if `target` is not `is_relative_to(
   quartz.app.paths.user_dir().resolve())` (e.g. `preset_subdir` with `".."`), `report({"ERROR"},
   "preset path outside the user directory")` and `{"CANCELLED"}`, without creating a directory or writing or
   deleting anything; (d) only then, on creation, `Path(dir).mkdir(parents=True, exist_ok=True)`. Removal (`remove_name` or `remove_active`):
   deletes the file if it exists (missing → `report({"WARNING"}, …)`), returns `{"FINISHED"}`. Creation:
   empty `name` → `{"FINISHED"}` without writing; otherwise writes UTF-8: `"import bpy\n"`, each line of
   `getattr(self, "preset_defines", [])`, then `f"{path} = {value!r}\n"` for each path in
   `self.preset_values`, with `value = eval(path, ns)` in a namespace `ns = {"bpy": bpy, "context":
   context}` where the `preset_defines` lines were executed beforehand; `quartz.math` and
   `PropArray` values become `tuple`; returns `{"FINISHED"}`. Nothing is created or written outside
   `quartz.app.paths.user_dir()` (§0.1(5)): the cancellation in step (c) comes before any effect
   (through `quartz.ops.call`, it becomes `OperatorFailedError`, §2.1.8). Order of the written lines
   = order of `preset_defines` and of `preset_values`; the file ends with `"\n"`.
2. The annotations use the factories of the `bpy.props` shim (fidelity of `deferred.function`); the shim
   imports `bpy` with an alias (`import bpy as _bpy`, rule 4), and the annotations MUST reference the
   alias `_bpy` (a name resolvable in the module globals: in Python 3.14 annotations are evaluated
   lazily against those globals, and `own_annotations`, §1.6.6, would silently ignore an annotation that
   cites `bpy`). Public names: `compat/bl_ui/utils.py`
   only `PresetPanel`; `compat/bl_operators/presets.py` only `AddPresetBase`; `compat/idprop/types.py`,
   `compat/rna_prop_ui.py` and `compat/bl_math.py` exactly the names in the block.
3. The mixins are original text (clean-room): only the public shape matches Blender.

Errors: `OperatorFailedError` with `"preset path outside the user directory"` (via `quartz.ops.call`).

#### 3.1.7 `docs/COMPAT.md`

Human-readable document in English, with the authorship line `> Quartz — author: **D1on1n**.` and exactly these
`##` sections (in this order; `tests/arch/test_compat_thin.py` checks the titles):

1. `## Activation and modes` — `activate`/`deactivate`/`activated`, fixtures `bpy`/`bpy_lenient`, strict ×
   lenient (§3.0.3), use in the CLI and in the sweep.
2. `## Blender 5.2.2 profile` — origin (dump), fields, counts [O], regeneration (`python
   tools/gen_compat_profile.py`, `--check`).
3. `## compat to quartz mapping` — the table from ARCHITECTURE §8 updated with the names of this contract.
4. `## Phantom surface and missing-symbol log` — UI placeholders, phantom types, phantom collections,
   `None` context members, missing operators, `missing_symbols()`, `classify_symbol`.
5. `## Deliberate divergences` — the 13 from ARCHITECTURE §13, plus: `bpy.app` is a module (no
   *struct sequence* fields), libraries `supported=False`, neutral `build_*`, fake `build_options`,
   `bpy.app.icons` not implemented, `bpy.msgbus` without automatic delivery, minimal `PresetPanel`/`AddPresetBase`,
   `bl_ui`/`bl_operators` only with `utils`/`presets`,
   an operator that does not exist in Quartz fails as nonexistent even if it exists in Blender (the profile says whether it
   exists in 5.2.2); plus, a closed list coming from the sibling tasks (which do not edit this file):
   `Color.from_acescg_to_scene_linear`/`from_scene_linear_to_acescg` missing (§3.2.6);
   `BVHTree.FromObject` ignores modifiers and uses object space (§3.2.1); `update_edit_mesh`
   writes to the mesh immediately (§3.3.1); the old edit BMesh stays alive after leaving edit
   mode (§3.3.1); `bmesh.ops` defaults = the slot's "zero" (§3.3.4); `triangulate` `BEAUTY` without the
   angle criterion (§3.3.4); the `imbuf` module has no shim (out of scope for the milestone). Item 13 of
   ARCHITECTURE §13 is worded according to §1.4.9 (implemented in `mathutils.noise`: `random`,
   `seed_set`, `random_unit_vector`, `random_vector`).
6. `## Schema divergences` — the categories of §2.4.5 and where the `DIVERGENCES` dictionaries live.
7. `## Probe divergences` — one line per `DIVERGENCES` entry in `tests/contract/`,
   containing the literal key (e.g. `` `operator_basic.calls` ``) and the reason.

#### 3.1.8 Tests

Isolation (§0.6): the code of this task uses only L1 and L2 (ready at the start of L3), so all the
tests below pass before the sibling tasks exist, except the cases that import sibling shims —
symbols of `mathutils`, `bpy_extras`, `bmesh`, `addon_utils` and `gpu` in `test_usage_surface.py`,
`math.*` facts of `test_contract_judge_facts.py` and the identities of
`mathutils`/`bmesh`/`bpy_extras`/`addon_utils` in `test_compat_thin.py` —, which go in their own
test functions and pass at the L3 gate. Every test that activates compat uses `bpy`/`bpy_lenient` (or `qz`
+ `activate`/`deactivate` in `try/finally`) and calls `quartz.compat.clear_missing()` before
checking counts. Tests in `tests/contract/` use the `bpy` fixture (strict), except
`test_contract_profile.py` and the coverage checks, which do not need a session. Test classes
use the prefix `QZT_` (reproduced probes keep the probe's `QUARTZPROBE_*`/`quartz_probe.*`
names). Tests that touch `sys.modules`, `os.environ` or `quartz.app.paths` undo the change in
`finally`/`monkeypatch` and call `quartz.app.paths.reset()` afterwards.

- `tests/compat/test_activate.py` — sequence of §3.0.3: `sys.path[0]` is `compat_dir()`;
  `settings.api_prefix == "bpy"`, `lenient_ui == (not strict)`, `record_missing` true; hooks
  (`repr(bpy.data.objects["Cube"]) == "bpy.data.objects['Cube']"` **[O]**, and `"quartz.data…"` after
  `deactivate`); resolver installed/removed; idempotence (2nd `activate(strict=False)` only changes the
  strictness); fake `bpy` module (`types.ModuleType("bpy")`, no `__file__`) in `sys.modules` →
  `CompatError` `"already loaded"` and nothing changed (removed in `finally`);
  `blender_version=(4, 2, 0)` → `"unsupported Blender version"`; `blender_version=(5, 2, 2)` accepted;
  import failure (`monkeypatch.setenv("QUARTZ_COMPAT_DIR", tmp_path)` with a `bpy/__init__.py` that
  raises `RuntimeError("qzt boom")`, `paths.reset()`) → `RuntimeError` propagated, `"bpy"` out of
  `sys.modules` and settings/hooks/resolver/`sys.path`/`is_active()` restored; `deactivate`
  after changing `QUARTZ_COMPAT_DIR` still removes the original `sys.path` entry; `deactivate` removes every module
  in `SHIM_MODULES`, unregisters classes of `COMPAT_OWNER`, restores to the default the adapters installed by a shim
  imported during activation and preserves the log; in a subprocess `[sys.executable, "-I", "-c",
  ...]` (without `quartz.extras` loaded): `import mathutils` inside `activated()` and, outside it,
  `BVHTree.FromObject` → `NotImplementedError` of §1.4.9; in the same format,
  `quartz.extras.install_adapters()` first, `classify_symbol("mathutils.Vector")` with compat
  inactive and, afterwards, the adapter remains installed; reentrant `activated`;
  `note_missing`/`missing_symbols` (copy)/`clear_missing`, `record_missing=False` does not record;
  `quartz.ops.call("qz_nope.nope")` → `OperatorNotFoundError` with `'"bpy.ops.qz_nope.nope"'` and record
  `"bpy.ops.qz_nope.nope"`; `classify_symbol` with one case per rule of §3.1.1 (`bpy.types.Object` /
  `bpy.types.Bone` / `bpy.types.QZ_nope` → IMPLEMENTED/PHANTOM/MISSING; `bpy.data.objects`,
  `bpy.data.actions`, `bpy.data.qz_nope`; `bpy.context.scene`, `bpy.context.space_data`;
  `bpy.ops.object.mode_set`, `bpy.ops.object.qz_nope`; `bpy.app.version`, `bpy.app.icons.release`,
  `bpy.app.qz_nope`; `bpy.data.all_ids`, `bpy.data.filepath`; `os.path` → `ValueError`), without recording
  (`missing_symbols()` unchanged) and working with compat inactive (stays inactive afterwards) and active
  lenient (`bpy.types.QZT_MT_unknown` → PHANTOM only in lenient); `resolve_type("Object")` and
  `resolve_type("Struct")` → `None`; `CONTEXT_IMPLEMENTED ⊆ set(CONTEXT_MEMBERS) |
  set(CONTEXT_METHODS)` and `len == 33`; `UI_NAME_RE is quartz.compat.profile.UI_NAME_RE`.
- `tests/compat/test_identity.py` — each identity of §3.1.3–§3.1.6 (`is`), including
  the 39 handler lists, `persistent`, timers, translations (except `locale`/`locales`, compared by
  value and live after `set_locale`), `bpy.utils` (44 names), `previews`, `units`, `bpy.path` (17),
  `bpy.msgbus` (3, without `flush`), `idprop.types`, `rna_prop_ui`, `bl_math`, `bpy.ops.mesh is
  quartz.ops.mesh`; `bpy.data is quartz.data` and `bpy.context is quartz.context`; `from bpy import data`
  survives `quartz.session.reset()`; under `restrict_blend(enabled=True)` `bpy.data.objects` →
  `RestrictedAccessError`; the 14 `sys.modules` names of §3.1.3 (1); set of public names of
  each shim of this task equal to the listed one (rule 4, with the exact definition of "public name"),
  including no `annotations` and no module without a `_` alias besides the own submodules
  listed in §3.1.3–§3.1.6.
- `tests/compat/test_types_view.py` — aliases (`bpy_struct`, `Struct`, `Property`, `Context`…);
  catalog; operator registered with `bpy.utils.register_class` visible as `QZT_OT_x` and absent after
  unregistering (strict → `AttributeError` + 1 record); profile placeholder (`VIEW3D_MT_object`,
  `CYCLES_CAMERA_PT_dof`, `UI_UL_list` coming from the catalog): subclass of `quartz.types.Menu`/`Panel`,
  stable identity, `owner_of == COMPAT_OWNER`, `append`/`is_extended` **[O]**, recorded once,
  unregistered by `deactivate`; phantom `Bone` (base `Struct`) and `Action` (base `ID`):
  `bl_rna.identifier`, dynamic extension and `del`, `PointerProperty(type=bpy.types.Action)` reads `None`;
  `bpy.types.install_hooks` → `AttributeError`; strict: `QZT_MT_unknown` → `AttributeError` with
  `"module 'bpy.types' has no attribute 'QZT_MT_unknown'"`; lenient (`bpy_lenient`): synthesized; unknown
  name outside the UI form → `AttributeError` in both modes; `bl_parent_id` pointing to a
  profile panel registers without error; `dir(bpy.types)` contains aliases, catalog, registered ones and the 4023.
- `tests/compat/test_props_filter.py` — 10 factories + `RemoveProperty`/`_PropertyDeferred` (identity);
  `function is bpy.props.IntProperty` and `keywords` of the dump `props.__deferred__` **[O]**; `repr` of the
  deferred; `meta` and unknown kwarg → `TypeError`; positionals; `items`/`type` required;
  for the 10 factories, `set(profile().props_kwargs[f]) == set(quartz.props.PROPERTY_KWARGS[f])` and each
  kwarg accepted; `bpy.msgbus.flush` → `AttributeError` recorded;
  `bpy.types.Scene.qz_x = bpy.props.IntProperty(default=5)` → `scene.qz_x == 5` **[O]**; PropertyGroup
  with `bpy.props` annotations registers, reads defaults and unregisters with no leftovers.
- `tests/compat/test_app_shim.py` — versions **[O]**; `_FORWARDED` names equal to `quartz.app` (including
  `tempdir` after changing `QUARTZ_USER_DIR`); libraries `supported is False`; `build_*` are `bytes`;
  `build_options.cycles is False`; every name in `profile().app["attributes"]` except `count`, `index`,
  `n_fields`, `n_sequence_fields`, `n_unnamed_fields` exists in `bpy.app`; handlers (39 + `persistent`,
  no Quartz-only names, `fn._bpy_persistent` **[O]**); a registered timer does not fire on its own **[O]**;
  translations (names from the dump, `pgettext*` identity in `en_US` **[O]**); icons →
  `NotImplementedInQuartz`; unknown attribute → `AttributeError` recorded as `"bpy.app.qz_nope"`.
- `tests/compat/test_usage_surface.py` — each symbol of `blender_usage["tiers"]["tier1"]` (22):
  `classify_symbol == "IMPLEMENTED"` and resolves by import + chained `getattr`; each symbol of
  `easy_core["exact"]`: resolves and `!= "MISSING"`; each `tier2` symbol equal to `bpy.context` or
  with prefix `bpy.types.`, `bpy.data.` or `bpy.context.`: `∈ {"IMPLEMENTED", "PHANTOM"}`. Symbols
  whose top is from a sibling (`mathutils`, `bpy_extras`, `bmesh`, `addon_utils`, `gpu`) in separate functions.
  "Resolves" = `importlib.import_module(<top>)` and chained `getattr` (with submodule import when
  the attribute is missing), under the `bpy` fixture, without exception.
- `tests/contract/conftest.py` — fixtures `probes` (`blender_dump["probes"]`), `facts`
  (`blender_facts`) and `probe_error` (function `str -> tuple[type[BaseException], str]` that splits
  the probes' `"BuiltinType: message"` at the first `": "` and resolves the type in `builtins`; text without
  that format or a type that is not a builtin exception → `ValueError`). Each `test_contract_*.py` (except
  `test_contract_profile.py`) defines, as module literals, `CHECKED: set[str]` and `DIVERGENCES:
  dict[str, str]` (key → reason in English, never empty). Key format: `"<probe>.<key>"`
  for probe keys of the dump (probe names have no dot) and `"fact:<fact>"` or
  `"fact:<fact>:<subkey>"` for judge facts. A key MAY be in both when only part of the
  value is checked (the reason says which part is not). Each file checks, for each probe it
  owns, `set(probes[probe]) == {c for "<probe>.<c>" in CHECKED ∪ DIVERGENCES}`, and that each fact it
  owns appears in at least one `"fact:<fact>…"` key. Errors compare the probe's builtin
  (`isinstance`) and fragments of this contract, never the whole text; the script reproduces that of the
  homonymous probe in `tools/dump_bpy_api.py` / `tools/probe_judge_facts.py` (same names and values; these
  files are read, never imported or edited).
- `tests/contract/test_contract_registration.py` — probes `registration_errors`, `required_bl_attrs`
  and fact `register.classmethod_hooks` **[O]**: fragments of §2.1.6 (`"Must contain 1 '.' character"`,
  `"Invalid character at position 0"`, `"maximum length is 60"`, `'class to have an "bl_label"
  attribute'`, `'enum "NOPE" not found in ('`, `"parent 'QUARTZPROBE_PT_none'"`, `"already registered
  as a subclass"`, `"missing bl_rna attribute"`, `"(may not be registered)"`); leading digit and panel name
  outside the convention accepted; required attributes per base exactly those of the probe.
- `tests/contract/test_contract_operator.py` — probes `operator_basic`,
  `operator_poll_false_and_returns` and fact `ops.defaults` **[O]**: returns, `idname()`,
  `in_bpy_types_as`, fragments of §2.1.8 (`'keyword "nope" unrecognized'`, `'enum "Z" not found in'`,
  `"expected an int type, not str"`, `"1-2 args execution context is supported"`, `'Calling operator
  "bpy.ops.quartz_probe.hello" error, could not be found'`, `"Operator
  bpy.ops.quartz_probe.nopoll.poll() probe poll message"`, `"incompatible return value"`, `"'DONE' not
  found in ("`, `"expected a set, not a NoneType"`, `"Error: Python:"` + `"probe failure"`, `"Error:
  probe error report"`), clamping at 10, `poll` before the kwargs; `calls` with one `poll` per call
  (divergence 2) in `DIVERGENCES`.
- `tests/contract/test_contract_props.py` — probe `property_semantics` and facts `props.pg_attrs`,
  `props.scalar_coercion`, `props.enum_get_set` **[O]** (registration before the item, clamp, `update`
  always called, get/set with enum integer, `maxlen` in bytes, flags, pointer, collection, `keys()` in
  order of the 1st write, `repr` `"bpy.data.scenes['Scene'].qz_attr_pg"`).
- `tests/contract/test_contract_idprops.py` — probe `idprop_storage` **[O]** (RNA props outside
  `keys()`, `KeyError` `'key "quartz_probe_val" not found'`, types `IDPropertyArray`/`IDPropertyGroup`,
  exact `as_dict`, `property_unset` returns to the default).
- `tests/contract/test_contract_id.py` — probe `id_semantics` and facts `id.order`,
  `id.order_after_rename`, `id.rename`, `id.users`, `data.filepath_unsaved`, `object.defaults`,
  `repr.data_objects`, `repr.mesh`, `repr.vertex`, `repr.scene_collection` **[O]**; `edge_keys` as a
  set (divergence 6; key in `CHECKED` and `DIVERGENCES`); `id_semantics.orphans_purge_returns`
  (5 in Blender) in `DIVERGENCES` (Quartz's factory scene has fewer IDs, §2.6.1); the returned value
  is only checked as an `int` equal to the number of IDs that disappeared from `bpy.data`;
  `set(profile().data_collections) == set(COLLECTION_NAMES)`.
- `tests/contract/test_contract_context.py` — probe `context_semantics` and facts `modes`,
  `object.select_get_unlinked` **[O]** (`temp_override`, unknown member invisible, `'attribute
  "scene" from "Context" is read-only'`, `path_resolve`, `mode_set`/`EDIT_MESH`, `POSE` → `TypeError`
  with `'enum "POSE" not found in ('`, primitive/translate/delete with orphan mesh).
- `tests/contract/test_contract_undo_handlers.py` — probe `undo_and_handlers` **[O]**: polls of
  `ed.*`, `"Operator bpy.ops.ed.undo.poll()"`, `undo_push` on, `use_global_undo`, `_bpy_persistent`,
  `frame_change_pre` already with the new frame, types `(Scene, Depsgraph)` in `post`, timer does not fire, msgbus without
  delivery before `flush()` (`msgbus_notified_sync == 0`); `undo_and_handlers.handler_log` stays
  in `CHECKED` (`frame_change_pre`/`frame_change_post` entries and the 1st `depsgraph_update_post`) and in
  `DIVERGENCES` (presence or absence of `depsgraph_update_post` in the 2nd `frame_set` is not checked;
  the 2nd argument of `frame_change_pre` is `None` in Blender and the `Depsgraph` in Quartz, §2.2.8, rule 6).
- `tests/contract/test_contract_ui.py` — probe `ui_extension_points` **[O]**: `is_extended`
  false→true, silent double `remove`, `Counter(profile().ui_types.values()) == {"MT": 685,
  "PT": 1233, "HT": 26, "UL": 33}` (= the probe's `builtin_*_count`), the 10 menus/panels of
  `common_menus_present` resolve in strict (placeholders), keyconfig `addon` not `None`, keymap item
  `["object.select_all", "A", "PRESS", 1]`; `ui_extension_points.draw_funcs_len` (2 in
  Blender) in `DIVERGENCES` (Quartz does not keep the original `draw` in the function list: 1).
- `tests/contract/test_contract_judge_facts.py` — remaining judge facts: `path.*`, `math.*`,
  `translations.*`, `utils.*`, `factory`, `primitives`, `ops.select_all`, `ops.duplicate`,
  `object.matrix_world` (D9: `fact:object.matrix_world:before_update` and
  `fact:object.matrix_world:child_world_no_update` in `DIVERGENCES` — in Quartz the updated value already holds),
  `light.swap` (divergence 4: `fact:light.swap:cls_after` and `fact:light.swap:has_angle` in
  `DIVERGENCES` — the instance becomes `SunLight` and has `angle`; `energy_after == 10.0` checked),
  `mesh.shade`. Coverage tables (module literals): `COVERED_ELSEWHERE: dict[str, str]` (fact
  → name of the `tests/contract/` file that checks it) and `PROBES_COVERED: dict[str, str]` (probe →
  file). The test checks: `set(facts) == {facts with a "fact:" key in this file} |
  set(COVERED_ELSEWHERE)` (disjoint sets); `set(PROBES_COVERED) == set(probes) -
  {"addon_lifecycle"}`; and, for each entry of the two tables, that the source text of the indicated file
  contains `f'"fact:{fact}'` or `f'"{probe}.'` (reading the file, without importing it).
- `tests/contract/test_contract_profile.py` (does not use `bpy`) — `load_profile() ==
  profile_from_dict(generate_profile(blender_dump))`; `profile_to_text(generate_profile(dump))` ==
  bytes of `blender_5_2.json` decoded as UTF-8; `generate_profile` called twice gives the same
  text; counts **[O]** (39, 71, 40, 4023, 685/1233/26/33, 11, 116, 19, 2499, 45);
  `profile().version_string == "5.2.2 LTS"`, `version_file == (5, 2, 45)`; the JSON text does not
  contain `"generated_at"`, `"C:\\"` or `"Users"`, and `app["attributes"]` of `binary_path`, `tempdir`,
  `cachedir` has no `"value"`;
  `tools/gen_compat_profile.py --check` returns 0 (subprocess with `sys.executable`, `cwd` = root) and 1
  with `--out` pointing to an altered copy in `tmp_path` (under the root, §1.1.2); `--out` outside the root
  → 2 (with `--check` and without); nonexistent `--dump` → 2; invalid profile (wrong `format`, `format_version` 2,
  missing field, broken JSON in `tmp_path`) → `CompatError` `"invalid compat
  profile"`; `quartz.compat.profile()` always returns the same object.
- `tests/arch/test_compat_thin.py` — without compat active, by AST over the existing files of
  `compat/` (ignoring `__pycache__` and entries starting with `.`): `compat/__init__.py` does not exist;
  top-level names of `compat/` (folders and `*.py` without extension) ⊆ `SHIM_MODULES`; no
  file with more than 300 lines; no `def`/`class` with a body of more than 80 lines; no `numpy`
  import; module-level `class` only in `compat/bl_ui/**`, `compat/bl_operators/**`,
  `compat/bpy/app/**`, `compat/gpu/**`, `compat/gpu_extras/**`, `compat/blf.py`, `compat/aud.py`;
  `docs/COMPAT.md` exists with the authorship line and exactly the 7 `##` titles of §3.1.7, in that
  order; each key of the `DIVERGENCES` literal (read by AST) of each `tests/contract/test_contract_*.py`
  appears between backticks in the `## Probe divergences` section. With the `bpy` fixture: sample of identities of this
  task (`bpy.types.Object`, `bpy.utils.register_class`, `bpy.path.abspath`, `bpy.app.handlers.load_post`,
  `idprop.types.IDPropertyGroup`, `bl_math.clamp`) and, in separate functions, of the siblings
  (`mathutils.Vector is quartz.math.Vector`, `bmesh.new is quartz.bmesh.new`,
  `bpy_extras.io_utils.ImportHelper is quartz.extras.io_utils.ImportHelper`, `addon_utils.check` exists).

### 3.2 `quartz.extras` and math, GPU and audio shims (`l3-compat-math-extras`)

This task delivers `quartz.extras` (native equivalent of `bpy_extras`, plus the
`BVHTree.FromObject` adapter) and the shims `mathutils`, `bpy_extras`, `gpu`, `gpu_extras`, `blf` and `aud`.
It consumes from L1: `quartz.math` (§1.4), `quartz.geometry` (§1.5), `quartz.props` (§1.6.1),
`quartz.rna.hooks` (§1.6.2), `quartz.rna.annotations` (§1.6.6), `Struct.is_property_set` (§1.6.7),
`quartz.path` (§1.1.6), `quartz.app.translations` (§1.2.5), `quartz.app.paths.compat_dir` (§1.2.7,
tests only) and `quartz.errors` (§1.3). From L2, only through the index: the data protocol of `Mesh`
(`q_geometry`, RNA collections of §2.3.1, by duck typing), `Object.mode`/`type`/`matrix_world`/`data`
(§2.2.6), `quartz.types.object.object_type_for` (§2.2.6), `WindowManager.fileselect_add` and
`invoke_props_dialog` (§2.2.10), `Camera.view_frame` (§2.3.3), `BlendDataImages.load`/`new` and
`Image.filepath`/`filepath_raw`/`reload` (§2.3.5), `Operator.q_properties_class` (§2.5.2),
`quartz.operators.common.object_data_add` (§2.7.2), `quartz.session.api_data()` (§2.6.1) and the
context members of §2.6.2 (`active_object`, `collection`, `scene`, `space_data`, `area`,
`preferences`, `blend_data`, `window_manager`); in tests only, `quartz.ops.call`,
`quartz.testing.invoke_operator`/`rna_schema_diff` (§2.6.3, §2.6.8) and `quartz.registry.is_registered`
(§2.5.1). It uses no other L3 task.

Marker **[L]**: see §2.0.3 (here, a reading of the Python `bpy_extras` of Blender 5.2.2; implement as
written; a future golden prevails).

General rules of the section:

1. **No import effect** (§3.0.2): no `quartz.extras.*` module installs an adapter, registers a
   class or imports a sibling L2 module at module level; imports of `quartz.operators`,
   `quartz.session` and `quartz.types` stay **inside the functions** that use them, so that each module
   imports (and is testable) before the siblings exist (§0.6). The only import effect is that of the
   `compat/mathutils` shim (`quartz.extras.install_adapters()`).
2. **NI rule**: every function or class of this section marked `# NI` calls
   `quartz.rna.hooks.note_missing(symbol)` and raises `NotImplementedInQuartz(symbol)` on call
   (or on construction), where `symbol` is the Blender name (`"bpy_extras.anim_utils.bake_action_objects"`,
   `"gpu.shader.from_builtin"`); GPU/audio stubs also pass `detail` (§3.2.8, rule 1). Every
   NI function/class, every callable returned by `_stub.unavailable`, every class of
   `_stub.stub_class` and each phantom of `mathutils.geometry` has `_q_phantom = True` (read by
   `quartz.compat.classify_symbol`, §3.1.1, rule 6).
3. Each `quartz/extras/*.py` module defines `__all__` with exactly the public names listed in its
   signature block; the `compat/bpy_extras` shims re-export that `__all__` (identity; sole
   exception: `bpy_extras.wm_utils.progress_report`, §3.2.7 rule 1).
4. `compat/` files of this task import only stdlib, `quartz.*` and other shims, **never numpy**
   (§0.5); each fits within the line budget of `tests/arch/test_compat_thin.py` (§3.1.8).
5. Mixins (`ImportHelper`, `ExportHelper`, `AddObjectHelper`) **do not** inherit from `Struct`: they declare
   properties by annotation only (`_PropertyDeferred` from `quartz.props`), collected in the MRO of the
   user's operator at registration (§1.6.6) **[O]**.

#### 3.2.1 `quartz/extras/__init__.py` and `quartz/extras/bvh.py`

```python
# extras/__init__.py — NO import side effects
SUBMODULES: tuple[str, ...] = ("anim_utils", "asset_utils", "bmesh_utils", "bvh", "image_utils", "io_utils",
                               "keyconfig_utils", "mesh_utils", "node_shader_utils", "node_utils", "object_utils",
                               "view3d_utils", "wm_utils")
__all__ = ("SUBMODULES", "install_adapters")
def install_adapters() -> None     # quartz.math.bvhtree.set_object_adapter(quartz.extras.bvh.from_object); idempotent
def __getattr__(name: str) -> ModuleType
    # name in SUBMODULES -> importlib.import_module(f"quartz.extras.{name}"); otherwise
    # AttributeError(f"module 'quartz.extras' has no attribute '{name}'")
def __dir__() -> list[str]         # sorted(set(SUBMODULES) | {"SUBMODULES", "install_adapters"})

# extras/bvh.py
__all__ = ("from_object",)
def from_object(object, depsgraph, *, deform: bool = True, render: bool = False, cage: bool = False,
                epsilon: float = 0.0) -> BVHTree      # quartz.math.BVHTree
```

`extras/__init__.py` imports `quartz.extras.bvh` only inside `install_adapters` (no submodule is
imported when the package is imported).

Rules for `install_adapters`:

1. Installs `quartz.extras.bvh.from_object` as the object adapter of `quartz.math.bvhtree`
   (§1.4.9); calling it again installs the same object (idempotent). Callers: the
   `compat/mathutils` shim (§3.2.6), `quartz.cli.main` (§3.5.1) and tests. Undone by:
   `quartz.compat.deactivate()` and the exit of `quartz.testing.isolated()`
   (`set_object_adapter(None)`, §3.0.2); this task does not define a removal function.
2. Once installed, `quartz.math.BVHTree.FromObject(ob, dg, deform=..., render=..., cage=...,
   epsilon=...)` forwards the arguments to `from_object` and returns the result.

Rules for `from_object`:

1. Mesh data via duck typing: `geo = getattr(getattr(object, "data", None), "q_geometry", None)`;
   if `geo` is not `quartz.geometry.MeshGeometry` → `ValueError` with
   `f"Object '{name}' has no mesh data"` (`name = getattr(object, "name", "?")`) **[I]** (Blender
   also rejects objects without an evaluable mesh; own wording).
2. Uses `geo` as is: no modifier evaluation (`deform`, `render`, `cage` are accepted and
   ignored) and no writing of the edit BMesh (an object in `EDIT` uses the last written geometry; whoever
   needs the edit state calls `object.update_from_editmode()` first) **[I]**. `depsgraph` is accepted and
   ignored (MAY be `None`).
3. Triangulates with `quartz.geometry.triangulate(geo)` → `(tris_corner, tri_face)`;
   `tris_vert = geo.corner_verts[tris_corner]` (shape `(T, 3)`); returns
   `BVHTree._q_from_triangles(geo.positions, tris_vert, tri_face, epsilon)` in **object space**
   (no `matrix_world`) **[I]**. The `index` of queries is therefore the index of the mesh polygon.
   No writes to the mesh or the object (pure query; does not stamp dirtiness, §2.2.3).
4. Mesh without faces → empty tree (every query returns the four-`None` tuple, §1.4.9).

#### 3.2.2 `quartz/extras/io_utils.py`

```python
AXIS_IDENTIFIERS: tuple[str, ...] = ("X", "Y", "Z", "-X", "-Y", "-Z")      # order of the axis items [L]
PATH_REFERENCE_MODES: tuple[str, ...] = ("AUTO", "ABSOLUTE", "RELATIVE", "MATCH", "STRIP", "COPY")   # [L]
class ImportHelper:                                  # mixin
    filepath: StringProperty(name="File Path", description=<own text>, maxlen=1024, subtype="FILE_PATH", options={"SKIP_SAVE"})
    # filename_ext / filter_glob: defined by the subclass (nothing is injected)
    def invoke(self, context, _event) -> set[str]                    # fileselect_add(self) -> {"RUNNING_MODAL"}
    def invoke_popup(self, context, confirm_text: str = "") -> set[str]
    def check(self, _context) -> bool
class ExportHelper:                                  # mixin
    filepath: StringProperty(name="File Path", description=<own text>, maxlen=1024, subtype="FILE_PATH", options={"SKIP_SAVE"})
    check_existing: BoolProperty(name="Check Existing", description=<own text>, default=True, options={"HIDDEN"})
    check_extension: ClassVar[bool | None] = True     # class attribute (not a prop)
    # filename_ext: str — REQUIRED class attribute of the subclass
    def invoke(self, context, _event) -> set[str]
    def check(self, _context) -> bool
def orientation_helper(axis_forward: str = "Y", axis_up: str = "Z") -> Callable[[type], type]
axis_conversion = quartz.math.axis_conversion        # same object
def axis_conversion_ensure(operator, forward_attr: str, up_attr: str) -> bool
def unpack_list(list_of_tuples) -> list
def unpack_face_list(list_of_tuples) -> list
def path_reference(filepath: str, base_src: str, base_dst: str, mode: str = "AUTO", copy_subdir: str = "",
                   copy_set: set | None = None, library=None) -> str
def path_reference_copy(copy_set: set, report: Callable[[str], None] = print) -> None
path_reference_mode: _PropertyDeferred
    # EnumProperty(name="Path Mode", description=<own text>,
    #              items=tuple((m, m.capitalize(), <own text>) for m in PATH_REFERENCE_MODES), default="AUTO")
def unique_name(key, name: str, name_dict: dict, name_max: int = -1, clean_func: Callable | None = None,
                sep: str = ".") -> str
def poll_file_object_drop(context) -> bool
__all__ = ("AXIS_IDENTIFIERS", "PATH_REFERENCE_MODES", "ImportHelper", "ExportHelper", "orientation_helper",
           "axis_conversion", "axis_conversion_ensure", "unpack_list", "unpack_face_list", "path_reference",
           "path_reference_copy", "path_reference_mode", "unique_name", "poll_file_object_drop")
```

Descriptions (`description=`) and item names do not come from the dump (the mixins are not in it): own
wording, free, in English. Rules (behavior **[L]**):

1. `ImportHelper.invoke`: `context.window_manager.fileselect_add(self)` and returns
   `{"RUNNING_MODAL"}`. Headless, `quartz.ops.call` with `INVOKE_DEFAULT` falls back to `execute` (§2.1.8,
   **[O]**), so `invoke` only runs with `settings.invoke_in_background` or
   `quartz.testing.invoke_operator`.
2. `ImportHelper.invoke_popup(context, confirm_text="")`: if `self.properties.is_property_set(
   "filepath")` → `context.window_manager.invoke_props_dialog(self, confirm_text=confirm_text,
   title=os.path.basename(self.filepath), translate=False)` (the WM only records the request, §2.2.10); otherwise
   `self.invoke(context, None)`.
3. `ImportHelper.check` = the axis part of `ExportHelper.check`: if the instance has `axis_forward` and
   `axis_up` → `axis_conversion_ensure(self, "axis_forward", "axis_up")`; otherwise `False`.
4. `ExportHelper.invoke`: if `self.filepath` is empty, builds `base + self.filename_ext` with `base =
   os.path.splitext(context.blend_data.filepath)[0]` or, with no saved file,
   `quartz.app.translations.pgettext_data("untitled")`; then `fileselect_add(self)` →
   `{"RUNNING_MODAL"}`. Without `filename_ext` on the class → natural `AttributeError`.
5. `ExportHelper.check`: `axis_changed` as in rule 3; if `check_extension is not None` and
   `os.path.basename(self.filepath)` is not empty: with `check_extension` true, the new path is
   `quartz.path.ensure_ext(os.path.splitext(filepath)[0], self.filename_ext)` (the current extension is
   **replaced**: `"a.txt"` → `"a.fbx"`); with false, the path is kept; if different, writes it to
   `self.filepath`. Returns `extension_changed or axis_changed` (extension changed or axis changed).
6. `orientation_helper(axis_forward="Y", axis_up="Z")` returns a class decorator that adds
   two entries to the decorated class's **own** annotations (replacing same-named ones; the decorator
   returns the class itself): `axis_forward = EnumProperty(name="Forward", items=tuple((a,
   f"{a} Forward", "") for a in AXIS_IDENTIFIERS), default=axis_forward, update=<f>)` and `axis_up =
   EnumProperty(name="Up", items=tuple((a, f"{a} Up", "") for a in AXIS_IDENTIFIERS),
   default=axis_up, update=<u>)`; a new `_PropertyDeferred` per decorated class. `f(self, context)`:
   if `self.axis_forward[-1] == self.axis_up[-1]`, writes `self.axis_up = sign(axis_up) +
   "XYZ"[("XYZ".index(letter) + 1) % 3]` (sign = `"-"` if `axis_up` starts with `"-"`, otherwise `""`);
   `u(self, context)`: symmetric, writing `axis_forward` **[L]**. The write triggers the `update` of the
   other prop (§1.6.4, step 8), which no longer finds a conflict. Examples: `forward="Y", up="Z"`;
   writing `axis_up = "Y"` → `axis_forward == "Z"`; with `up="Z"`, writing `axis_forward = "-Z"` →
   `axis_up == "X"`. The defaults are not validated (forward and up on the same letter are accepted, as in
   Blender **[L]**).
7. The decorator MUST NOT reassign an existing `__annotations__` nor touch the annotations of bases or
   mixins (ARCHITECTURE §14; the `cls.__annotations__ = …` trick erases annotations in 3.14).
   Mandatory implementation, in this order:
   1. `"__annotations__"` in `cls.__dict__` (Python 3.13 with annotations, `from __future__ import
      annotations`, or an explicit dict) → adds the entries to **that** dict, in place;
   2. otherwise, on Python ≥ 3.14: `old = cls.__annotate__` (the `type` descriptor reads only the
      class's own function; `None` if it has no own annotations); writes
      `cls.__annotate__ = annotate` (assignment through the `type` descriptor) with `annotate(format)` that,
      for `Format.VALUE`, `Format.FORWARDREF` and `Format.STRING`, returns
      `{**(annotationlib.call_annotate_function(old, format) if old else {}), **new}` (in
      `STRING` the new ones as `repr(deferred)`) and raises `NotImplementedError` for the other formats;
      then removes `"__annotations_cache__"` from `cls.__dict__` if it exists (`type.__delattr__`), so
      that a `cls.__annotations__` read before decoration does not go stale;
   3. otherwise (Python 3.13 without own annotations) → creates `cls.__annotations__ = dict(new)` (there is no
      dict to erase).

   In all cases `quartz.rna.annotations.own_annotations(cls)` sees the original annotations
   plus the two new ones, and `own_annotations(base)` of every base/mixin stays the same. A class already registered only
   sees the props after registering again **[I]**.
8. `axis_conversion_ensure(op, fa, ua)`: reads the two attributes; if the final letters coincide,
   replaces the one in `ua` with the next of `"XYZ"` (cyclic, keeping the sign), writes both and returns
   `True`; otherwise `False` without writing **[L]**.
9. `unpack_list`: flattens one level (`[(1, 2), (3,)]` → `[1, 2, 3]`). `unpack_face_list`: output of
   size `4 · len(input)`, each tuple occupying 4 positions (unused position = 0); triangle
   `(a, b, c)` with `c == 0` becomes `(b, c, a)`; quad `(a, b, c, d)` with `c == 0` or `d == 0` becomes
   `(c, d, a, b)` **[L]**; tuple of size outside `{3, 4}` → `ValueError` with `"3 or 4"` **[I]**.
   Both return a new `list` (input untouched).
10. `path_reference`: `abs = os.path.normpath(quartz.path.abspath(filepath, start=base_src,
    library=library))`; `MATCH` → `RELATIVE` if `filepath` starts with `"//"`, otherwise `ABSOLUTE`;
    `AUTO` → `RELATIVE` if `quartz.path.is_subdir(abs, base_dst)`, otherwise `ABSOLUTE`; `COPY` → destination
    `os.path.join(os.path.normpath(base_dst), copy_subdir, os.path.basename(abs))` (without
    `copy_subdir` if empty), appends `(abs, destination)` to `copy_set` and proceeds as `RELATIVE` on
    the destination; `ABSOLUTE` → `abs`; `RELATIVE` → `os.path.relpath(abs, base_dst)` (on `ValueError`,
    e.g. different drives, returns the absolute path); `STRIP` → `os.path.basename(abs)` **[L]**. A mode
    outside `PATH_REFERENCE_MODES` → `ValueError` with `f"invalid mode '{mode}'"`; `COPY` with
    `copy_set is None` → `ValueError` with `"requires copy_set"` **[I]**.
11. `path_reference_copy`: for each `(source, destination)` in `sorted` order: nonexistent source →
    `report(f"missing {source!r}, not copying")`; `os.path.exists(destination)` and
    `os.path.samefile(source, destination)` → nothing; otherwise `os.makedirs(dirname(destination), exist_ok=True)`
    and `shutil.copy(source, destination)` (I/O error propagates) **[L]**; empty `copy_set` → nothing. Writes only where the caller says (tests:
    `tmp_path`, §0.1(5)).
12. `unique_name(key, name, name_dict, ...)`: if `name_dict.get(key)` is not `None`, returns that
    value without writing; otherwise `base = name if clean_func is None else clean_func(name)` and:
    `name_max == -1` → candidate `base`, and while it is among the **values** of `name_dict`,
    `f"{base}{sep}{n:03d}"` with `n = 1, 2, …`; another `name_max` → candidate `base[:name_max]`, and on
    collision `base[:name_max - (len(f"{n:03d}") + 1)] + sep + f"{n:03d}"` (the separator counts as one
    character, whatever its length). Writes `name_dict[key] = candidate` and returns it
    **[L]**. E.g.: `name_max=6`, `name="abcdefgh"` → `"abcdef"`; with `"abcdef"` already among the values
    → `"ab.001"`.
13. `poll_file_object_drop(context)`: `area = getattr(context, "area", None)`; `None` → `False`
    (always headless); otherwise `area.ui_type in {"VIEW_3D", "OUTLINER"}` **[I]**.

#### 3.2.3 `quartz/extras/object_utils.py`

```python
class AddObjectHelper:                               # mixin
    def align_update_callback(self, _context) -> None   # align == "WORLD" -> self.rotation = (0.0, 0.0, 0.0) [L]
    # (defined BEFORE the annotations: in 3.13 they are evaluated immediately)
    align: EnumProperty(name="Align", items=(("WORLD", "World", <own text>), ("VIEW", "View", <own text>),
                        ("CURSOR", "3D Cursor", <own text>)), default="WORLD", update=align_update_callback)
    location: FloatVectorProperty(name="Location", size=3, subtype="XYZ_LENGTH", unit="LENGTH", min=-1e12, max=1e12,
                                  soft_min=-1000.0, soft_max=1000.0, step=1.0, precision=3, options={"SKIP_SAVE"})
    rotation: FloatVectorProperty(name="Rotation", size=3, subtype="EULER", unit="ROTATION", min=-1e12, max=1e12,
                                  soft_min=-2 * math.pi, soft_max=2 * math.pi, step=10.0, precision=3, options={"SKIP_SAVE"})
    scale: FloatVectorProperty(name="Scale", size=3, subtype="XYZ_LENGTH", unit="LENGTH", min=-1e12, max=1e12,
                               soft_min=-1000.0, soft_max=1000.0, step=1.0, precision=3, options={"HIDDEN", "SKIP_SAVE"})
    # fields = ops.submodules["mesh"]["primitive_cube_add"]["props"][<name>] from the dump [O]
    # (defaults (0, 0, 0); limits ±1e12 read back as float32 as ±999999995904.0; align without SKIP_SAVE)
    @classmethod
    def poll(cls, context) -> bool                   # getattr(context, "scene", None) is not None and context.scene.library is None
def object_data_add(context, obdata, operator=None, name: str | None = None) -> "Object"
def add_object_align_init(context, operator) -> Matrix                 # 4x4
def object_add_grid_scale(context) -> float
def object_add_grid_scale_apply_operator(operator, context) -> None
def world_to_camera_view(scene, obj, coord) -> Vector
def object_report_if_active_shape_key_is_locked(obj, operator) -> bool  # False (no shape keys in the milestone)
__all__ = ("AddObjectHelper", "object_data_add", "add_object_align_init", "object_add_grid_scale",
           "object_add_grid_scale_apply_operator", "world_to_camera_view",
           "object_report_if_active_shape_key_is_locked")
```

Rules:

1. `add_object_align_init(context, operator)` — `P = operator.properties` if `operator` is not
   `None` (otherwise `P = None`); the steps run in this order:
   1. Snapshot **before any write** (writing `align` triggers `align_update_callback`, which
      zeroes `rotation`, §1.6.4 step 8): `loc_set = P.is_property_set("location")`, `rot_set =
      P.is_property_set("rotation")`, `align_set = P.is_property_set("align")` and the copies
      `Vector(P.location)`, `Euler(P.rotation)` (all false/absent without `P`).
   2. Location: `Vector(P.location)` (copy from step 1) if `loc_set`, otherwise
      `Vector(context.scene.cursor.location)`; with `P`, writes `P.location = local` **[L]**.
   3. Alignment: `P.align` if `align_set`; otherwise `"VIEW"` if
      `getattr(context.preferences.edit, "object_align", "WORLD") == "VIEW"`, otherwise `"WORLD"`; with
      `P` and `not align_set`, writes `P.align = alignment` **[L]** (`PreferencesEdit` has no
      `object_align` in the milestone: the default `"WORLD"` applies).
   4. Rotation: `rot_set` → `Euler(<copy from step 1>).to_matrix().to_4x4()` (any alignment);
      otherwise by alignment: `"WORLD"` → `Matrix.Identity(4)`; `"CURSOR"` →
      `Matrix(context.scene.cursor.matrix).to_3x3().to_4x4()`; `"VIEW"` →
      `Matrix(rv3d.view_matrix).to_3x3().inverted().to_4x4()` with
      `rv3d = getattr(getattr(context, "space_data", None), "region_3d", None)`, identity if
      `None` (always headless) **[I]**. With `P`, finally writes `P.rotation = rotation.to_euler()`.
   5. Returns `Matrix.Translation(local) @ rotation` (new 4×4); `scale` is not included **[L]**.
2. `object_data_add(context, obdata, operator=None, name=None)`:
   1. `ob = getattr(context, "active_object", None)`; if `ob is not None`, `ob.mode == "EDIT"`,
      `obdata is not None` and `object_type_for(obdata) == ob.type` → before creating anything,
      `NotImplementedInQuartz("bpy_extras.object_utils.object_data_add", "edit mode join")` (Blender
      joins the data into the object being edited) **[I]**, with `hooks.note_missing` of the same
      symbol (NI rule).
   2. Otherwise returns `quartz.operators.common.object_data_add(context, obdata, name=name,
      matrix=add_object_align_init(context, operator))` (creates, links into `context.collection`,
      deselects the others, selects and activates — §2.7.2) **[L]**. Errors from `object_type_for`
      (`PropertyTypeError` for an unregistered data type) and from §2.7.2 propagate.
3. `object_add_grid_scale(context)`: `space = getattr(context, "space_data", None)`; if
   `getattr(space, "type", None) == "VIEW_3D"` → `float(space.overlay.grid_scale_unit)`; otherwise `1.0`
   **[L]**.
4. `object_add_grid_scale_apply_operator(operator, context)`: `g = object_add_grid_scale(context)`;
   for each prop `p` of `operator.properties.bl_rna.properties` (except `"rna_type"`) not set
   (`is_property_set(p, ghost=False)` false) with `unit == "LENGTH"` and `subtype == "DISTANCE"`:
   `setattr(operator, p, getattr(operator, p) * g)` — even with `g == 1.0` (the prop becomes set)
   **[L]**.
5. `world_to_camera_view(scene, obj, coord)`: `co = obj.matrix_world.normalized().inverted() @
   Vector(coord)`; `z = -co.z`; frame = `obj.data.view_frame(scene=scene)`; non-`ORTHO` camera: if
   `z == 0.0` returns `Vector((0.5, 0.5, 0.0))`, otherwise each corner `(cx, cy, cz)` becomes
   `(cx·z/(−cz), cy·z/(−cz))`; `x = (co.x − min_x)/(max_x − min_x)` and `y = (co.y − min_y)/(max_y −
   min_y)` with minimums/maximums over the **four** corners (independent of the order of `view_frame`);
   returns `Vector((x, y, z))` — `(0, 0)` = bottom-left corner of the frame, `z` = depth
   in front of the camera **[L]**.

#### 3.2.4 `quartz/extras/view3d_utils.py`

```python
def region_2d_to_vector_3d(region, rv3d, coord) -> Vector
def region_2d_to_origin_3d(region, rv3d, coord, *, clamp: float | None = None) -> Vector
def region_2d_to_location_3d(region, rv3d, coord, depth_location) -> Vector | None   # None only in perspective with a ray parallel to the plane
def location_3d_to_region_2d(region, rv3d, coord, *, default=None) -> Vector | None
__all__ = ("region_2d_to_vector_3d", "region_2d_to_origin_3d", "region_2d_to_location_3d",
           "location_3d_to_region_2d")
```

Math only (`quartz.math`) on duck-typed objects: `region.width`, `region.height`;
`rv3d.is_perspective` (bool), `rv3d.view_matrix`, `rv3d.perspective_matrix` (converted with
`Matrix(m)`, accept `Matrix` or 4×4 sequences) and `rv3d.view_perspective` (`"PERSP"`/`"ORTHO"`/
`"CAMERA"`) — `RegionView3D` names from Blender **[I]** (the dump only has the type name). Headless
there is no region: the caller supplies the objects. Notation: `nx = 2·coord[0]/width − 1`, `ny =
2·coord[1]/height − 1`, `Vi = view_matrix.inverted()`, `Pi = perspective_matrix.inverted()`.
Formulas **[L]**:

1. `region_2d_to_vector_3d`: perspective → `p = Vector((nx, ny, −0.5, 1.0))`, `q = Pi @ p`, vector
   `= (q.xyz / q.w) − Vi.translation`, normalized; orthographic → `−Vi.col[2].xyz` normalized.
2. `region_2d_to_origin_3d`: perspective → `Vi.translation` (copy); orthographic → `o =
   Pi.col[0].xyz·nx + Pi.col[1].xyz·ny + Pi.translation`, and then, if `clamp != 0.0` (this also holds
   for `clamp is None`) and `view_perspective != "CAMERA"`: `off = Pi.col[2].xyz`; if `clamp is not
   None`: with `clamp < 0`, `off = −off` and `clamp = −clamp`; if `off.length > clamp`, `off.length =
   clamp`; finally `o −= off` (with `clamp is None` the offset is the whole `off`).
3. `region_2d_to_location_3d`: `o = region_2d_to_origin_3d(region, rv3d, coord)`, `d =
   region_2d_to_vector_3d(region, rv3d, coord)`, `p = Vector(depth_location)`; perspective →
   `quartz.math.geometry.intersect_line_plane(o, o + d, p, Vi.col[2].xyz)` (without `no_flip`; parallel
   → `None` propagates); orthographic → `intersect_point_line(p, o, o + d)[0]`.
4. `location_3d_to_region_2d`: `prj = perspective_matrix @ Vector((x, y, z, 1.0))`; `prj.w > 0` →
   `Vector((w/2 + w/2·prj.x/prj.w, h/2 + h/2·prj.y/prj.w))` (`w`, `h` = region width/height);
   otherwise `default` (the same object passed in).

All return a new `Vector` with 3 components (2 in `location_3d_to_region_2d`); no input is
modified. `region.width`/`height` zero → natural `ZeroDivisionError` **[I]**.

#### 3.2.5 Remaining `quartz/extras/*.py`

```python
# anim_utils.py — everything NI (animation deferred, ARCHITECTURE §15)
def action_get_channelbag_for_slot(action, slot): ...            # NI
def action_ensure_channelbag_for_slot(action, slot): ...         # NI
def action_get_first_suitable_slot(action, target_id_type): ...  # NI
def animdata_get_channelbag_for_assigned_slot(anim_data): ...    # NI
def bake_action(obj, *, action, frames, bake_options): ...       # NI
def bake_action_objects(object_action_pairs, *, frames, bake_options): ...   # NI
def bake_action_iter(obj, *, action, bake_options): ...          # NI
def bake_action_objects_iter(object_action_pairs, bake_options): ...         # NI
class BakeOptions:                   # __init__(self, *args, **kwargs) -> NI("bpy_extras.anim_utils.BakeOptions")
    ...
class AutoKeying(metaclass=_NIMeta): # any class attribute without a leading "_" -> NI callable NI(f"bpy_extras.anim_utils.AutoKeying.{name}")
    ...
# node_utils.py
def connect_sockets(input, output): ...                          # NI
def find_node_input(node, name: str): ...                        # NI
def find_base_socket_type(socket): ...                           # NI
# node_shader_utils.py
class ShaderWrapper: ...                                         # __init__(self, *args, **kwargs) -> NI("bpy_extras.node_shader_utils.ShaderWrapper")
class PrincipledBSDFWrapper(ShaderWrapper): ...                  # same, symbol "...PrincipledBSDFWrapper"
class ShaderImageTextureWrapper: ...                             # same, symbol "...ShaderImageTextureWrapper"
def rgb_to_rgba(rgb) -> list[float]                              # [float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0]
def rgba_to_rgb(rgba) -> Color                                   # Color(rgba[:3]) (float32 components, §0.2)
# image_utils.py
def load_image(imagepath: str, dirname: str = "", place_holder: bool = False, recursive: bool = False,
               ncase_cmp: bool = True, convert_callback: Callable[[str], str] | None = None, verbose: bool = False,
               relpath: str | None = None, check_existing: bool = False, force_reload: bool = False) -> "Image | None"
# asset_utils.py
class SpaceAssetInfo:
    @staticmethod
    def is_asset_browser(space_data) -> bool         # False
    @staticmethod
    def is_asset_browser_poll(context) -> bool       # False
    @staticmethod
    def get_active_asset(context) -> None            # None
# mesh_utils.py
def edge_face_count_dict(mesh) -> dict[tuple[int, int], int]
def edge_face_count(mesh) -> list[int]
def edge_loops_from_edges(mesh, edges=None) -> list[list[int]]
def ngon_tessellate(from_data, indices, fix_loops: bool = True, debug_print: bool = True) -> list[tuple[int, int, int]]
def mesh_linked_triangles(mesh) -> list[list[object]]                 # MeshLoopTriangle items
def mesh_linked_uv_islands(mesh) -> list[list[int]]                   # polygon indices
# bmesh_utils.py
def bmesh_linked_uv_islands(bm, uv_layer): ...                   # NI
# wm_utils.py
class ProgressReport:                # no-op context manager: __init__(self, wm=None); enter_substeps(nbr, msg=""); step(msg="", nbr=1);
                                     #   leave_substeps(msg=""); initialize(wm=None); finalize(); __enter__ -> self; __exit__ -> None
class ProgressReportSubstep:         # same: __init__(self, progress, nbr, msg="", final_msg=""); enter_substeps; step; leave_substeps
progress_report: types.SimpleNamespace   # SimpleNamespace(ProgressReport=ProgressReport, ProgressReportSubstep=ProgressReportSubstep)
# keyconfig_utils.py
def keyconfig_test(kc) -> bool                                   # False (Quartz does not detect keymap conflicts)
```

The `__all__` of each module = the public names of its block above (`_NIMeta` is private; in
`wm_utils`, `("ProgressReport", "ProgressReportSubstep", "progress_report")`).

Rules:

1. `AutoKeying` uses the private metaclass `_NIMeta` whose `__getattr__` (only for names without a leading
   `_`; the others → `AttributeError`) returns a callable that, when called, follows the NI rule; the
   access itself neither raises nor records anything. `BakeOptions(...)` and the three shader wrappers raise NI in
   `__init__` (before any other effect). Functions marked `# NI` accept any argument (`*args,
   **kwargs` in the implementation; the names above document the Blender signature).
2. `load_image` **[L]**: candidates, in order, tested with `os.path.exists`:
   `quartz.path.abspath(imagepath)`; with `dirname`: `os.path.join(dirname, imagepath)` and
   `os.path.join(dirname, os.path.basename(imagepath))`; with `ncase_cmp`, a directory entry whose
   name matches case-insensitively; with `recursive` and `dirname`, the first occurrence of the base name
   in `os.walk(dirname)` (directories and files in `sorted` order, for determinism **[I]**).
   Found: `convert_callback(path)` if given (uses the return value); `img = quartz.session.api_data().
   images.load(path, check_existing=check_existing)` (§2.3.5: only registers the path);
   `relpath is not None` → `img.filepath_raw = quartz.path.relpath(path, start=relpath)`;
   `force_reload` → `img.reload()`; returns `img`. Not found: `place_holder` → `images.new(
   os.path.basename(imagepath), 128, 128)` with `filepath = imagepath`; otherwise `None`. `verbose`
   prints the attempts to `stdout`.
3. `mesh_utils` uses only the mesh RNA API (§2.3.1: `polygons[i].loop_indices`/`.vertices`/
   `.edge_keys`, `edges[i].key`/`.vertices`, `loops[i].edge_index`/`.vertex_index`,
   `loop_triangles`, `uv_layers.active.data[i].uv`), working on any mesh with the shape of bpy:
   1. `edge_face_count_dict` → edge key (ordered pair) → number of faces that use it; edges without a
      face do not appear. `edge_face_count` → list aligned with `mesh.edges` (0 for loose ones) **[L]**.
   2. `edge_loops_from_edges(mesh, edges=None)` (default: all edges): groups edges into chains
      of vertex indices; a closed chain repeats the starting vertex at the end; one list per chain;
      internal order is free **[L]**.
   3. `ngon_tessellate(from_data, indices, ...)`: `from_data` = sequence of coordinates or a mesh
      (`from_data.vertices[i].co`); returns triangles as **positions in `indices`** (not vertex
      indices) **[L]**, via `quartz.math.geometry.tessellate_polygon`; fewer than 3 → `[]`;
      `fix_loops` collapses consecutive positions with the same coordinate (the triangle uses the 1st) **[I]**;
      `debug_print` ignored.
   4. `mesh_linked_triangles`: connected components of `loop_triangles` by shared vertex
      (requires `calc_loop_triangles()` beforehand, as in Blender) **[L]**; groups ordered by the smallest
      triangle index and, within each group, triangles in ascending index order **[I]**.
   5. `mesh_linked_uv_islands`: components of polygons connected by an edge whose UVs (active layer)
      coincide at both vertices; no active UV layer → `[]` **[I]**; lists and items in
      ascending order **[I]**.
4. `wm_utils` neither prints nor calls the `WindowManager` (honest no-op; Blender prints progress)
   **[I]**.

#### 3.2.6 `compat/mathutils/**`

Files: `compat/mathutils/__init__.py`, `geometry.py`, `kdtree.py`, `bvhtree.py`, `noise.py`,
`interpolate.py`.

```python
# mathutils/__init__.py
from quartz.math import Vector, Matrix, Quaternion, Euler, Color          # same objects
MatrixAccess = type(Matrix.Identity(2).row)                               # [O] name in dir(mathutils)
from mathutils import geometry, kdtree, bvhtree, noise, interpolate       # shims
__all__ = ("Color", "Euler", "Matrix", "MatrixAccess", "Quaternion", "Vector",
           "bvhtree", "geometry", "interpolate", "kdtree", "noise")       # = dump extras.mathutils.__module__ [O]
quartz.extras.install_adapters()                                          # only effect of import (§3.0.2)
# geometry.py: the 19 names of quartz.math.geometry (§1.4.8, includes delaunay_2d_cdt) re-exported (same objects) +
#   PHANTOMS: intersect_line_line_2d, intersect_line_sphere_2d, intersect_plane_plane, intersect_point_line_segment,
#   intersect_point_quad_2d, intersect_sphere_sphere_2d, intersect_tri_tri_2d, points_in_planes   # NI when called
# kdtree.py: KDTree | bvhtree.py: BVHTree | noise.py: the 17 names of §1.4.9 | interpolate.py: poly_3d_calc   (same objects)
```

Rules:

1. Identity: `mathutils.Vector is quartz.math.Vector` (likewise the five classes and each function or
   class re-exported from the submodules); the `mathutils.<sub>` modules are shims of their own, not the
   `quartz.math` modules.
2. Each phantom in `geometry.py` is a function with the dump's name that follows the NI rule with the
   symbol `f"mathutils.geometry.{name}"`. Inventory **[O]**: the 27 names of
   `extras.mathutils.geometry` (19 re-exported + 8 phantoms), the 17 of `noise`, `KDTree`,
   `BVHTree`, `poly_3d_calc`. The re-exported names that L1 already declares as not implemented
   (`geometry.delaunay_2d_cdt` and the 13 of `noise` from §1.4.9) keep the L1 behavior
   (plain `NotImplementedError`, no `note_missing`): the shim does not wrap them (identity matters
   more).
   Each submodule defines `__all__` with exactly the names of the dump `extras.mathutils.<sub>`.
3. Class members come from `quartz.math` (L1); the shim adds no methods. Known
   divergence: `Color.from_acescg_to_scene_linear` and `Color.from_scene_linear_to_acescg` (in the dump
   **[O]**, outside §1.4.6) may be missing — the absence is recorded in the `DIVERGENCES` of
   `tests/compat/test_mathutils_shim.py` (the file `docs/COMPAT.md` belongs to `l3-compat-bpy`, §3.1.7;
   this task does not edit it).
4. Importing `mathutils` with compat inactive works if `compat_dir()` is in `sys.path` (the
   shims of this task do not import `bpy`); the adapter is installed the same way.

#### 3.2.7 `compat/bpy_extras/**`

Files: `compat/bpy_extras/__init__.py`; one shim per submodule — `anim_utils.py`,
`asset_utils.py`, `bmesh_utils.py`, `image_utils.py`, `io_utils.py`, `keyconfig_utils.py`,
`mesh_utils.py`, `node_shader_utils.py`, `node_utils.py`, `object_utils.py`, `view3d_utils.py` — and the
package `wm_utils/` (`__init__.py`, `progress_report.py`). `bvh` has no shim (it does not exist in
Blender).

```python
# bpy_extras/__init__.py
SUBMODULES: tuple[str, ...] = tuple(m for m in quartz.extras.SUBMODULES if m != "bvh")
__all__ = SUBMODULES
def __getattr__(name: str) -> ModuleType   # name in SUBMODULES -> importlib.import_module(f"bpy_extras.{name}"); otherwise note_missing + AttributeError
def __dir__() -> list[str]                 # sorted(SUBMODULES) ⊇ dump extras.bpy_extras (asset_utils, io_utils, node_utils, object_utils) [O]
# bpy_extras/<m>.py:  from quartz.extras.<m> import *   +   __all__ = quartz.extras.<m>.__all__
# bpy_extras/wm_utils/__init__.py: from quartz.extras.wm_utils import ProgressReport, ProgressReportSubstep
#                                  from bpy_extras.wm_utils import progress_report   # the SUBMODULE (not the SimpleNamespace)
#                                  __all__ = ("ProgressReport", "ProgressReportSubstep", "progress_report")
# bpy_extras/wm_utils/progress_report.py: from quartz.extras.wm_utils import ProgressReport, ProgressReportSubstep (same objects)
#                                  __all__ = ("ProgressReport", "ProgressReportSubstep")
```

Rules:

1. `bpy_extras.io_utils.ImportHelper is quartz.extras.io_utils.ImportHelper` (likewise every name of each
   `__all__`), with **one** exception: `bpy_extras.wm_utils.progress_report` is the shim module
   `bpy_extras.wm_utils.progress_report` (a package cannot have an attribute and a submodule with the same
   name; importing the submodule would overwrite the attribute), whereas
   `quartz.extras.wm_utils.progress_report` is the `SimpleNamespace`; both expose the same
   `ProgressReport`/`ProgressReportSubstep` objects. `from bpy_extras.wm_utils.progress_report import
   ProgressReport` works and returns `quartz.extras.wm_utils.ProgressReport`. No file in
   `compat/bpy_extras/**` defines a `class` (rule of §3.1.8).
2. `import bpy_extras` does not import the submodules (attribute access loads them); no effect
   other than re-exporting.
3. Unknown name in `bpy_extras` or in a shim submodule `bpy_extras.<m>` (module `__getattr__`):
   a name starting with `"__"` → `AttributeError` without noting; otherwise
   `quartz.rna.hooks.note_missing(f"{__name__}.{name}")` (e.g. `"bpy_extras.nope"`,
   `"bpy_extras.io_utils.nope"`) + `AttributeError(f"module '{__name__}' has no attribute
   '{name}'")`.

#### 3.2.8 `compat/gpu/**`, `compat/gpu_extras/**`, `compat/blf.py`, `compat/aud.py`

Files: `compat/gpu/__init__.py`, `_stub.py`, `capabilities.py`, `compute.py`, `matrix.py`,
`platform.py`, `select.py`, `shader.py`, `state.py`, `texture.py`, `types.py`;
`compat/gpu_extras/__init__.py`, `batch.py`, `presets.py`; `compat/blf.py`; `compat/aud.py`.
Top-level names **[O]** (dump `extras.gpu`/`blf`/`aud`); signatures and members of the submodules of
`gpu` **[I]** (the dump does not inventory them).

```python
# gpu/_stub.py (private; used by gpu*, gpu_extras*, blf, aud)
NO_GPU: str = "no GPU in headless Quartz"; NO_AUDIO: str = "no audio device in headless Quartz"
def unavailable(symbol: str, detail: str = NO_GPU) -> Callable[..., NoReturn]   # _q_phantom = True; call: quartz.rna.hooks.note_missing(symbol) + NotImplementedInQuartz(symbol, detail)
def stub_class(module: str, name: str, detail: str = NO_GPU) -> type
    # new class (__name__ = name, __module__ = module, _q_phantom = True) whose __init__ follows unavailable(f"{module}.{name}")
    # (quartz.rna.hooks.note_missing + NotImplementedInQuartz), and whose
    # metaclass __getattr__ returns, for a name without a leading "_", unavailable(f"{module}.{name}.{attr}") (the access does not
    # raise; the call does); name with a leading "_" -> AttributeError; isinstance/issubclass work normally
def module_getattr(module: str) -> Callable[[str], NoReturn]
    # module __getattr__: name with "__" -> AttributeError; otherwise quartz.rna.hooks.note_missing(f"{module}.{name}") +
    # AttributeError(f"module '{module}' has no attribute '{name}'")
# gpu/__init__.py
from gpu import capabilities, compute, matrix, platform, select, shader, state, texture, types
def init() -> None                                       # no-op
# gpu/state.py — no-op setters (accept any value); getters return a constant neutral value
def blend_set(mode: str) -> None; def blend_get() -> str                       # "NONE"
def depth_test_set(mode: str) -> None; def depth_test_get() -> str             # "NONE"
def depth_mask_set(value: bool) -> None; def depth_mask_get() -> bool          # False
def line_width_set(width: float) -> None; def line_width_get() -> float        # 1.0
def viewport_set(x: int, y: int, xsize: int, ysize: int) -> None; def viewport_get() -> tuple[int, int, int, int]   # (0, 0, 0, 0)
def scissor_set(x: int, y: int, xsize: int, ysize: int) -> None; def scissor_get() -> tuple[int, int, int, int]     # (0, 0, 0, 0)
def scissor_test_set(enable: bool) -> None; def color_mask_set(r: bool, g: bool, b: bool, a: bool) -> None
def face_culling_set(culling: str) -> None; def front_facing_set(invert: bool) -> None
def point_size_set(size: float) -> None; def program_point_size_set(enable: bool) -> None
def clip_distances_set(distances_enabled: int) -> None
def active_framebuffer_get() -> NoReturn                # NI (would return a resource)
# gpu/matrix.py — no-op; getters return a NEW identity Matrix (4x4; normal 3x3)
def load_identity() -> None; def load_matrix(matrix) -> None; def load_projection_matrix(matrix) -> None
def multiply_matrix(matrix) -> None; def translate(offset) -> None; def scale(scale) -> None; def scale_uniform(scale: float) -> None
def push() -> None; def pop() -> None; def push_projection() -> None; def pop_projection() -> None; def reset() -> None
def push_pop() -> ContextManager[None]; def push_pop_projection() -> ContextManager[None]
def get_model_view_matrix() -> Matrix; def get_projection_matrix() -> Matrix; def get_normal_matrix() -> Matrix
# gpu/shader.py
def from_builtin(shader_name: str, *, config: str = "DEFAULT") -> NoReturn   # NI
def create_from_info(shader_info) -> NoReturn            # NI
def unbind() -> None                                     # no-op
# gpu/types.py — stub_class: Buffer, GPUBatch, GPUFrameBuffer, GPUIndexBuf, GPUOffScreen, GPUShader, GPUShaderCreateInfo,
#   GPUStageInterfaceInfo, GPUTexture, GPUUniformBuf, GPUVertBuf, GPUVertFormat
# gpu/texture.py: def from_image(image) -> NoReturn  (NI)  |  gpu/compute.py: def dispatch(shader, groups_x_len, groups_y_len, groups_z_len) -> NoReturn (NI)
# gpu/select.py: def load_id(id: int) -> None  (no-op)
# gpu/platform.py
def backend_type_get() -> str        # "NONE"
def device_type_get() -> str         # "UNKNOWN"
def vendor_get() -> str; def renderer_get() -> str; def version_get() -> str      # ""
# gpu/capabilities.py — numeric *_get -> 0; *_support_get -> False; extensions_get -> ()
#   max_batch_indices_get, max_batch_vertices_get, max_images_get, max_texture_layers_get, max_texture_size_get,
#   max_textures_frag_get, max_textures_geom_get, max_textures_get, max_textures_vert_get, max_uniforms_frag_get,
#   max_uniforms_vert_get, max_varying_floats_get, max_vertex_attribs_get, max_work_group_count_get(index),
#   max_work_group_size_get(index), compute_shader_support_get, shader_image_load_store_support_get, hdr_support_get, extensions_get
# gpu_extras/__init__.py: from gpu_extras import batch, presets
# gpu_extras/batch.py:   def batch_for_shader(shader, type: str, content, *, indices=None) -> NoReturn      # NI
# gpu_extras/presets.py: def draw_circle_2d(position, color, radius: float, *, segments: int | None = None) -> NoReturn   # NI
#                        def draw_texture_2d(texture, position, width: float, height: float) -> NoReturn             # NI
# blf.py — the 24 names of the dump [O]
ROTATION: int = 1 << 0; CLIPPING: int = 1 << 1; SHADOW: int = 1 << 2; WORD_WRAP: int = 1 << 7
MONOCHROME: int = 1 << 11; NO_FALLBACK: int = 1 << 12          # values [I]; only names and distinctness are contract
def aspect(fontid: int, aspect: float) -> None; def clipping(fontid: int, xmin: float, ymin: float, xmax: float, ymax: float) -> None
def color(fontid: int, r: float, g: float, b: float, a: float) -> None; def enable(fontid: int, option: int) -> None
def disable(fontid: int, option: int) -> None; def draw(fontid: int, text: str) -> None; def draw_buffer(fontid: int, text: str) -> None
def position(fontid: int, x: float, y: float, z: float) -> None; def rotation(fontid: int, angle: float) -> None
def shadow(fontid: int, level: int, r: float, g: float, b: float, a: float) -> None; def shadow_offset(fontid: int, x: int, y: int) -> None
def size(fontid: int, size: float) -> None; def word_wrap(fontid: int, wrap_width: int) -> None      # all no-op
def dimensions(fontid: int, text: str) -> tuple[float, float]   # (0.0, 0.0)
def load(filepath: str) -> NoReturn                              # NI
def unload(filepath: str) -> None                                # no-op
def bind_imbuf(fontid: int, imbuf, display_name: str | None = None) -> NoReturn   # NI
types: types.SimpleNamespace                                     # empty namespace (Blender submodule with no headless use)
# aud.py — the 79 names of the dump [O]
# int constants (values [I], distinct within each prefix): AP_* (7), CHANNELS_* (9: INVALID 0, MONO 1, STEREO 2, STEREO_LFE 3,
#   SURROUND4 4, SURROUND5 5, SURROUND51 6, SURROUND61 7, SURROUND71 8), CODEC_* (9), CONTAINER_* (9), DISTANCE_MODEL_* (7),
#   FORMAT_* (7), RATE_* (11: RATE_<n> == n, RATE_INVALID 0), STATUS_* (4), STRETCHER_QUALITY_* (3)
# stub_class(..., detail=NO_AUDIO): AnimateableProperty, Device, DynamicMusic, HRTF, Handle, ImpulseResponse, PlaybackManager,
#   Sequence, SequenceEntry, Sound, Source, ThreadPool
class error(Exception): ...
```

Rules:

1. State change = no-op; state read = constant neutral value (does not remember the last
   `set`); creating or obtaining a GPU/audio resource = NI rule with `detail` `NO_GPU`/`NO_AUDIO`
   (`str(exc)` contains `"is not implemented in Quartz"` and `"headless"`) **[I]** (Blender in
   background also refuses to draw; own text).
2. `gpu.platform.backend_type_get() == "NONE"`; `blf.dimensions(0, "abc") == (0.0, 0.0)`.
3. Every module in this subsection, except the private `gpu._stub`, defines `__getattr__ =
   module_getattr(<dotted name>)` (e.g. `module_getattr("gpu.state")`); a top-level name from the dump
   never falls into it. In `blf.py`, the public name `types` is the `SimpleNamespace`; the stdlib module is imported
   under another name (`import types as _types`).
4. `gpu.<sub> is sys.modules["gpu.<sub>"]`; `import gpu` loads the nine submodules (and
   `gpu._stub`); nothing beyond that on import. Since `blf`, `aud` and `gpu_extras` import `gpu._stub`,
   importing them also loads the `gpu` package (accepted effect: it only re-exports, §3.0.2). The inventory tests
   check inclusion (dump names ⊆ `dir(module)`), not equality, because of `_stub`.
5. Neutral returns are **new** values on each call when mutable (`Matrix` from
   `gpu.matrix.get_*`) and immutable constants in the other cases.

#### 3.2.9 Tests

Local fixtures (defined in the files themselves; no new `conftest.py`):

- `adapter_reset`: `set_object_adapter(None)` on entry; `yield`; `set_object_adapter(None)` at the end
  (the default; the L1 tests run afterwards, §3.0.2).
- `shim_path`: if `"bpy"` is already in `sys.modules` (compat from another test leaked) →
  `pytest.fail("compat leaked")`; inserts `str(quartz.app.paths.compat_dir())` into `sys.path` if
  absent; at the end removes what it inserted, removes from `sys.modules` every name whose top-level is ∈
  `{"mathutils", "bpy_extras", "gpu", "gpu_extras", "blf", "aud"}` and calls
  `set_object_adapter(None)`. It allows testing the shims of this task **without** `quartz.compat` (§0.6);
  the integrations with `bpy` use the `bpy` fixture (§1.1.2).
- `missing_log`: `snap = hooks.snapshot()`; `hooks.install(note_missing=list.append)`; `yield
  list`; `hooks.restore(snap)`.

Tests that depend on siblings (session, registry, operators, datablocks, compat-bpy) are marked
"gate" and only need to pass at the L3 gate; the others run with L1 and this task only.

- `tests/extras/test_bvh_adapter.py`:
  - `import quartz.extras` does not change the adapter: `BVHTree.FromObject(...)` still raises
    `NotImplementedError` with `"adapter not installed"`; `dir(quartz.extras)` lists `SUBMODULES`;
    `quartz.extras.io_utils` loads by attribute.
  - `from_object` with a fake object (`SimpleNamespace(name="F", data=SimpleNamespace(q_geometry=
    MeshGeometry.from_pydata(<±1 cube with 8 vertices and 6 quads, the face with index 5 being the one at
    z = +1, built in the test itself>)))`) and `depsgraph=None`: `ray_cast((0, 0, 5), (0, 0, -1))` →
    local `(0, 0, 1)`, normal `(0, 0, 1)`, index `5`, distance `4.0` (`abs=1e-6`);
    `find_nearest((0, 0, 3))` → distance `2.0`; empty `MeshGeometry()` → miss of four `None`;
    `from_object` does not modify `geo` (copy of `positions` equal before/after).
  - No mesh (`data=None`, `data=SimpleNamespace()`) → `ValueError` with `"has no mesh data"`.
  - `install_adapters()` twice (with `adapter_reset`): `FromObject(fake, None, epsilon=0.0)`
    returns a tree equivalent to that of `from_object`; `deform/render/cage` accepted.
  - Gate (`qz`): factory Cube — `FromObject(cube, qz.context.evaluated_depsgraph_get())` hits the
    top face at `z = 1` in object space even after `cube.location = (5, 0, 0)`.
- `tests/extras/test_io_utils.py`:
  - `unpack_list`, `unpack_face_list` (`[(1, 2, 0)]` → `[2, 0, 1, 0]`; `[(1, 2, 0, 3)]` →
    `[0, 3, 1, 2]`; `[(1, 2, 3, 0)]` → `[3, 0, 1, 2]`; length `4·N`; `[(1, 2)]` →
    `ValueError` `"3 or 4"`).
  - `axis_conversion_ensure` on a plain object: `("Y", "Y")` → up `"Z"` and `True`; `("-Z", "Z")` → up
    `"X"`; `("Y", "-Y")` → up `"-Z"`; no conflict → `False` and nothing written.
  - `axis_conversion is quartz.math.axis_conversion`.
  - `path_reference` in `tmp_path`: `ABSOLUTE`, `RELATIVE`, `STRIP`, `AUTO` inside and outside
    `base_dst`, `MATCH` with `"//x.png"` and with an absolute path, `COPY` (pair in `copy_set`, relative
    result with `copy_subdir`); invalid mode → `ValueError` `"invalid mode"`; `COPY` without
    `copy_set` → `ValueError` `"requires copy_set"`. `path_reference_copy` copies, ignores the same
    file and reports a missing source (`"missing"`).
  - `unique_name`: repeated key returns the same name; collision → `.001`, `.002`; `sep="_"` →
    `"_001"`; `name_max=6` with `"abcdefgh"` → `"abcdef"` and, when taken, `"ab.001"`; `clean_func`
    applied before the lookup.
  - `path_reference_mode` is `_PropertyDeferred` with `function is quartz.props.EnumProperty`, items
    whose identifiers are `PATH_REFERENCE_MODES` in order and default `"AUTO"`;
    `poll_file_object_drop(SimpleNamespace(area=None))` false and with `area.ui_type == "VIEW_3D"`
    true.
  - `orientation_helper` on plain classes, checked with `collect_annotations`/`own_annotations`:
    class with own annotations (`filter_glob`, `use_x`) keeps all and gains the two; the base
    `ImportHelper` and an intermediate mixin stay unchanged; class without own annotations gains only
    the two; class whose `__annotations__` was read **before** decorating sees the new ones afterwards;
    temporary module in `tmp_path` with `from __future__ import annotations` (string annotations)
    also preserves the originals; defaults `("-Z", "Y")` respected; item identifiers in
    `AXIS_IDENTIFIERS` order; two decorated classes do not share the same `_PropertyDeferred`.
  - `ImportHelper.invoke`/`ExportHelper.invoke` with a fake context (`window_manager` that records
    `fileselect_add`, `blend_data.filepath`): `{"RUNNING_MODAL"}`; empty export → `"untitled" +
    filename_ext`; with `"C:/p/scene.qz"` saved → `"C:/p/scene" + ext`. `ExportHelper.check`:
    `"a.txt"` → `"a.fbx"` and `True`; already correct → `False`; `check_extension = None` → `False`.
    `invoke_popup` with and without `filepath` set.
  - Gate (`qz`): operator `class T(ImportHelper, Operator)` decorated with `orientation_helper`
    registers; `quartz.ops.call("t.x", filepath="f.obj")` runs with `self.filepath == "f.obj"` and
    default axes; writing `axis_up = "Y"` on an instance changes `axis_forward` to `"Z"`;
    `filepath` has `SKIP_SAVE` and `check_existing` of `ExportHelper` has `HIDDEN` (via `bl_rna`).
- `tests/extras/test_object_utils.py`:
  - `world_to_camera_view` with a fake camera (`matrix_world` identity, `data.type`, `view_frame`
    returning the corners `(±1, ±0.5, -2)` in shuffled order): point `(0, 0, -10)` → `(0.5, 0.5,
    10)`; point at the top-right corner of the frame → `(1, 1, z)`; `z == 0` → `(0.5, 0.5, 0)`;
    `ORTHO` uses the unscaled frame.
  - `object_add_grid_scale` with `space_data=None` → `1.0`; with a fake `VIEW_3D` space
    (`overlay.grid_scale_unit = 2.0`) → `2.0`.
  - `object_report_if_active_shape_key_is_locked(obj, None) is False`.
  - Gate (`qz`): `add_object_align_init(qz.context, None)` = cursor translation and identity
    rotation; `object_data_add(qz.context, mesh)` creates an object linked to `"Collection"`, active and the only one
    selected, name = mesh name (or `name=`); registered operator
    `class A(AddObjectHelper, Operator)` (with `execute` that calls `object_data_add(context, mesh,
    operator=self)`) called with `location=(1, 2, 3)` → `matrix_world.translation == (1, 2, 3)`;
    `rotation=(0, 0, π/2)` **without** `align` → rotation ≈ `Matrix.Rotation(π/2, 4, "Z")` (the snapshot
    from step 1 prevents the write of `align` from zeroing it) and, after the call, `align == "WORLD"`;
    `align="CURSOR"` with rotated cursor → cursor rotation; `align="VIEW"` headless → identity;
    writing `align = "WORLD"` on an instance with non-zero `rotation` zeroes `rotation`;
    `rna_schema_diff(A.q_properties_class(), {k: v for k, v in <props of mesh.primitive_cube_add>
    .items() if k in {"align", "location", "rotation", "scale"}})` empty; `poll` true with a scene;
    active in `EDIT` + mesh → `NotImplementedInQuartz` with `"edit mode join"`;
    `object_add_grid_scale_apply_operator` on an operator with `size: FloatProperty(default=2.0,
    subtype="DISTANCE", unit="LENGTH")` and `other: FloatProperty(default=3.0)`: `size` becomes
    set (value `2.0` with `space_data` absent) and `other` remains unset.
- `tests/extras/test_view3d_utils.py` (L1 only):
  - Orthographic with identity matrices and a 200×100 region: `location_3d_to_region_2d((0, 0, 0)) ==
    (100, 50)`; `region_2d_to_vector_3d` = `(0, 0, -1)`; `region_2d_to_origin_3d((100, 50))` =
    `(0, 0, -1)`; `clamp=0.0` → `(0, 0, 0)`; `view_perspective="CAMERA"` → no offset;
    `clamp=-0.5` → inverted offset of length 0.5.
  - Perspective built in the test (view + projection, `is_perspective=True`): round trip
    `region_2d_to_location_3d(location_3d_to_region_2d(p), depth_location=p) ≈ p` for points in
    front (`abs=1e-3`, `float32` matrices); normalized vector; origin = eye position; point
    behind the eye → `default` (`None` and a sentinel object returned by identity).
  - Accepts matrices as nested tuples.
- `tests/extras/test_misc_extras.py`:
  - NI rule (with `missing_log`): each NI name from `anim_utils`, `node_utils`, `node_shader_utils`,
    `bmesh_utils` raises `NotImplementedInQuartz` whose `symbol` starts with `"bpy_extras."` and notes the
    same symbol; `AutoKeying.keytype` (access only) neither raises nor notes, `AutoKeying.keytype()` →
    NI with `"AutoKeying.keytype"`; `AutoKeying._x` → `AttributeError`; `BakeOptions()` and
    `PrincipledBSDFWrapper(None)` → NI; `object_data_add` in edit mode already covered in
    `test_object_utils.py`. Each of these NI names has `_q_phantom is True`.
  - `rgb_to_rgba((0.1, 0.2, 0.3)) == [0.1, 0.2, 0.3, 1.0]`; `rgba_to_rgb(...)` is `Color`.
  - `SpaceAssetInfo` returns `False`/`False`/`None`; `keyconfig_test(None) is False`;
    `ProgressReport` as a context manager with `enter_substeps/step/leave_substeps` with no output on
    `stdout` (`capsys`); `progress_report.ProgressReport is ProgressReport`.
  - Each `quartz.extras` module has `__all__` equal to the block of §3.2.1–§3.2.5 and imports without
    `quartz.session` in `sys.modules` (checked in a `-I` subprocess with the root in `sys.path`).
  - Gate (`qz_empty`): mesh of two side-by-side quads + one loose edge via `from_pydata`:
    `edge_face_count_dict` (shared edge → 2; loose one absent), aligned `edge_face_count`
    (loose → 0); `edge_loops_from_edges` on a square of 4 edges → one list of 5 indices with the
    1st equal to the last; `ngon_tessellate` of a pentagon → 3 triangles with positions in
    `range(5)`; `mesh_linked_triangles` with two islands → 2 groups; `mesh_linked_uv_islands` with continuous UVs
    → 1 island, with a seam → 2.
  - Gate (`qz`): `load_image` finds the file directly, by `dirname` + base name, by `recursive`, case-
    insensitively; missing → `None`; `place_holder=True` → `Image` 128×128 with `filepath`;
    `relpath` writes a relative `filepath_raw`; `convert_callback` receives the found path.
- `tests/compat/test_mathutils_shim.py`:
  - With `shim_path`: `mathutils.Vector is quartz.math.Vector` (and the other four);
    `mathutils.MatrixAccess is type(Matrix().row)`; `set(__all__) ==
    set(blender_dump["extras"]["mathutils"]["__module__"])`; for each `<sub>`, `set(mathutils.<sub>.
    __all__) == set(dump["extras"]["mathutils"][<sub>])` and each name that `quartz.math.<sub>` also
    has is the same object (`is`); the 8 phantoms of `geometry` (the dump names absent from
    `quartz.math.geometry`) → `NotImplementedInQuartz` with `"mathutils.geometry.<name>"`,
    noted (`missing_log`) and with `_q_phantom is True`; `mathutils.noise.noise` is `quartz.math.noise.noise` (L1 exception
    preserved).
  - Members of the five classes (`extras.mathutils.<Class>` from the dump) exist on instances
    (`Vector` with 4 components for the swizzles with `w`), except `DIVERGENCES = {"Color.
    from_acescg_to_scene_linear": "...", "Color.from_scene_linear_to_acescg": "..."}` (reasons in
    English; absence is allowed, presence too).
  - Importing `mathutils` installs the adapter (`FromObject` on a fake object works); in the next
    test of the file (without `shim_path`; pytest preserves file order), `FromObject` goes back to
    raising `"adapter not installed"` and `"mathutils" not in sys.modules`.
  - Gate (`bpy`): `bpy.context.object` (Cube) with `mathutils.bvhtree.BVHTree.FromObject(ob,
    bpy.context.evaluated_depsgraph_get())` hits `(0, 0, 1)`; after `quartz.compat.deactivate()`
    the adapter is at the default and `"mathutils" not in sys.modules`.
- `tests/compat/test_bpy_extras_shim.py`:
  - With `shim_path`: for each submodule of `SUBMODULES`, every name in `__all__` is the same object as in
    `quartz.extras.<m>`; `bpy_extras.object_utils` loads by attribute; `dir(bpy_extras)` ⊇ the 4
    names of the dump **[O]**; `"bvh"` is not a submodule; `from bpy_extras.wm_utils.progress_report import
    ProgressReport` (identity); `bpy_extras.wm_utils.progress_report` is a module (the exception to rule
    1 of §3.2.7; the identity test skips it) with `ProgressReport is
    quartz.extras.wm_utils.ProgressReport`; unknown name → `AttributeError` noted as
    `"bpy_extras.<name>"`.
  - Gate (`bpy`): minimal add-on in a temporary module (`ImportHelper` + `orientation_helper` +
    `AddObjectHelper` on a second operator) registers via `bpy.utils.register_class`; `bpy.ops.<mod>.
    <op>(filepath=...)` returns `{"FINISHED"}`; `object_data_add` through the operator creates the object in
    `bpy.data.objects`; unregisters without residue (`quartz.registry.is_registered` false).
- `tests/compat/test_gpu_blf_stubs.py` (with `shim_path` and `missing_log`):
  - `_q_phantom is True` on `gpu.shader.from_builtin`, `gpu.types.GPUOffScreen` (a `stub_class`
    class) and on the callable returned by `gpu.types.GPUBatch.foo`;
  - `import gpu` exposes the 10 names of the dump **[O]**; `gpu.state.blend_set("ALPHA")`,
    `viewport_set(...)`, `gpu.matrix.load_matrix(...)`, `with gpu.matrix.push_pop(): ...` do
    nothing; neutral readers (`blend_get() == "NONE"`, `viewport_get() == (0, 0, 0, 0)`,
    `line_width_get() == 1.0`, `get_model_view_matrix() == Matrix.Identity(4)`, new copies on each
    call); `gpu.platform.backend_type_get() == "NONE"`.
  - NI: `gpu.shader.from_builtin("UNIFORM_COLOR")`, `gpu.types.GPUOffScreen(64, 64)`,
    `gpu.types.GPUBatch.foo()` (access without a call does not raise), `gpu.state.active_framebuffer_get()`,
    `gpu.texture.from_image(None)`,
    `gpu_extras.batch.batch_for_shader(None, "TRIS", {})`, `blf.load("x.ttf")` → 
    `NotImplementedInQuartz` with `"headless"` in the text and the symbol noted; `isinstance(exc,
    NotImplementedError)`.
  - `blf`: the 24 names of the dump; distinct `int` constants; `blf.size/position/draw` no-op;
    `blf.dimensions(0, "abc") == (0.0, 0.0)`.
  - `aud`: the 79 names of the dump; distinct `int` constants within each prefix;
    `aud.RATE_44100 == 44100`, `aud.CHANNELS_STEREO == 2`; `aud.Device()` and `aud.Sound.file("x.wav")`
    → NI with `"headless"`; `issubclass(aud.error, Exception)`.
  - Unknown name (`gpu.state.nope`, `blf.nope`, `aud.nope`) → `AttributeError` and annotation
    `"gpu.state.nope"`/`"blf.nope"`/`"aud.nope"`; `hasattr(gpu.state, "__wrapped__")` false without
    annotation.
  - No file in `compat/gpu`, `compat/gpu_extras`, `compat/blf.py`, `compat/aud.py`,
    `compat/mathutils`, `compat/bpy_extras` imports `numpy` (local `ast` analysis, complements
    `tests/arch/test_layering.py`).

### 3.3 `quartz.bmesh` (`l3-bmesh`)

`quartz.bmesh` is the edit mesh with the shape of Blender's `bmesh` module: linked elements
(vertices, edges, faces, loops), sequences, per-element data layers, a subset of
`bmesh.ops`, `bmesh.utils` and `bmesh.geometry`, the `Mesh` ↔ `BMesh` conversion, and the edit-mode
hooks (§2.1.9). The `compat/bmesh` shim only re-exports (identity). The public Blender names come from
`data/blender_api_dump.json`, key `extras.bmesh` (`__module__`, `types`, `ops`, `utils`,
`geometry`) **[O]**; the dump lists only names: the signatures, defaults and semantics below are Quartz's own,
marked **[I]** where there is no observation.

General rules of the task:

1. **Dependencies** (§0.5, §0.6): at module level, `quartz/bmesh/*.py` imports only stdlib, numpy,
   `quartz.errors`, `quartz.math` (including `quartz.math.bvhtree`), `quartz.geometry`,
   `quartz.rna.hooks` (all L1) and its own modules. The only L2 import, `quartz.types.mesh`, is
   done **inside** `install_adapters()`; the conversion handles the mesh by duck typing (`MeshLike`
   protocol, §3.3.3). This way `types`, `ops`, `utils`, `geometry` and the core of `convert` are
   testable before `l2-datablocks` exists. Internal graph with no import cycle: `convert`, `ops` and
   `utils` import `types` at module level; `types` imports `convert` only inside
   `BMesh.from_mesh/from_object/to_mesh`; `__init__` imports `convert` only inside its functions.
   Inside `quartz/bmesh/` the L1 geometry is imported by absolute name
   (`import quartz.geometry as qgeo`), so it is not confused with the submodule `quartz.bmesh.geometry`.
2. **No import side effects** (§3.0.2): importing any `quartz.bmesh.*` MUST NOT install an adapter
   or a hook. Only `install_adapters()` installs (called by `from_edit_mesh`, by the
   `compat/bmesh` shim, by `quartz.cli.main` and by tests).
3. **Not RNA structs**: the BM types are plain Python classes with `__slots__` (no `bl_rna`, outside
   `quartz.types`). Assigning an unknown attribute → `AttributeError` **[I]** (behavior of a
   slotted type). `__eq__`/`__hash__` are those of `object` (identity): elements and layers work as
   `dict`/`set` keys. Public members that exist only in Quartz carry the prefix `q_`; internal ones, `_q_` (§0.2).
4. **Float32 at rest**: `co`, `normal`, and `float`/`float_vector`/`float_color`/`color`/`uv` values
   are stored as `float32`; reading a scalar returns a `float` of the `float32` value (§0.2). Each
   element owns its own small numpy arrays (`co` `(3,)`, `normal` `(3,)`, one per vector layer
   value), NEVER views of a shared array that grows: this way a returned `Vector`
   stays alive after `verts.new`. Vectors returned by an attribute are
   `quartz.math.Vector._q_wrap(view, owner=elem)` over that memory (`v.co.x += 1` writes to the
   vertex); assigning (`v.co = (1, 2, 3)`) copies, requiring a sequence of numbers of the right size
   (wrong size → `PropertyValueError` with the attribute name, e.g. `"co"`; non-numeric →
   `PropertyTypeError`). Results of `calc_*` and `calc_volume`: scalars are `float` of the value
   rounded to `float32` (computations in `float64`); vectors are new, unwrapped `Vector`s.
5. **Errors**: invalid value → `quartz.errors.PropertyValueError` (inherits `ValueError`); invalid
   type → `quartz.errors.PropertyTypeError` (`TypeError`); index → builtin `IndexError`; dead
   data → `quartz.errors.RemovedStructError` (`ReferenceError`); dump surface not
   implemented → `NotImplementedInQuartz(<Blender symbol>)`, with symbols
   `f"bmesh.ops.{name}"`, `f"bmesh.utils.{name}"`, `f"bmesh.types.{Type}.{member}"`. An unsupported parameter of an implemented function uses the function's symbol and the parameter in `detail`:
   `NotImplementedInQuartz("bmesh.ops.delete", "context='TAGGED_ONLY'")` (text
   `"bmesh.ops.delete is not implemented in Quartz: context='TAGGED_ONLY'"`, §1.3). `quartz.bmesh`
   does not call `hooks.note_missing` (the symbol goes in the exception). The 60 NI ops of `bmesh.ops`, the 10
   NI functions of `bmesh.utils` and the NI members of the BM types have `_q_phantom = True` (read by
   `quartz.compat.classify_symbol`, §3.1.1, rule 6). Tests check the base builtin +
   fragments.
6. **Determinism**: no ordering depends on `id()`/hash; sequences iterate in creation order
   (except `sort`); returned `dict`s and lists follow input/creation (insertion) order.

#### 3.3.1 `quartz/bmesh/__init__.py`

```python
__all__ = ("new", "from_edit_mesh", "update_edit_mesh", "install_adapters", "types", "ops", "utils", "geometry")
from quartz.bmesh import types, ops, utils, geometry      # submodules (no import side effects)
def new(use_operators: bool = True) -> "BMesh"
    # empty, unwrapped BMesh; use_operators accepted and ignored (ops always available) [I]
def from_edit_mesh(mesh: "Mesh") -> "BMesh"
    # edit BMesh stored in mesh.q_edit_data (created on the 1st call); same instance on later calls
def update_edit_mesh(mesh: "Mesh", loop_triangles: bool = True, destructive: bool = True) -> None
    # writes the edit BMesh to the mesh right away (divergence [I])
def install_adapters() -> None
    # quartz.math.bvhtree.set_bmesh_adapter(quartz.bmesh.convert.bvh_from_bmesh);
    # quartz.types.mesh.set_editmode_hooks(flush=quartz.bmesh.convert.flush_edit_mesh); idempotent
```

`from_edit_mesh(mesh)`, in this order:

1. `install_adapters()` (ensures the `flush` hook before an edit BMesh exists; §3.0.2).
2. `mesh` without a `q_geometry` attribute → `PropertyTypeError` with `"expected a Mesh"` **[I]**.
3. `getattr(mesh, "is_editmode", False)` false → `PropertyValueError` with `"must be in editmode"`
   **[I]**.
4. `mesh.q_edit_data` is a live `BMesh` → returns it (identity: two calls return the same
   object).
5. Otherwise: `bm = BMesh()`; `quartz.bmesh.convert.mesh_to_bmesh(mesh, bm)`; marks `bm` as wrapped
   (`is_wrapped = True`, `bm.q_mesh = mesh`); `select_mode` comes from
   `quartz.rna.hooks.current_context().scene.tool_settings.mesh_select_mode` (vector of 3 booleans →
   the matching `{"VERT","EDGE","FACE"}`; context `None`, missing attribute or none true →
   `{"VERT"}`) **[I]**; `mesh.q_edit_data = bm`; returns `bm`.

`update_edit_mesh(mesh, loop_triangles=True, destructive=True)`:

1. Steps 2 and 3 of `from_edit_mesh` (same errors).
2. `mesh.q_edit_data` is not a live `BMesh` → nothing to write (no-op) **[I]**.
3. `quartz.bmesh.convert.flush_edit_mesh(mesh)` called **directly** (does not depend on the `flush`
   hook being installed; `q_set_geometry` stamps `"GEOMETRY"`); then, if `loop_triangles` and the
   mesh has `calc_loop_triangles`, calls it. `destructive` is accepted and ignored. In Blender the
   mesh is only updated on leaving edit mode; in Quartz `mesh.vertices` reflects the BMesh right
   after `update_edit_mesh` (divergence declared for `docs/COMPAT.md`) **[I]**.

`install_adapters()`: calls `quartz.math.bvhtree.set_bmesh_adapter(convert.bvh_from_bmesh)`; imports
`quartz.types.mesh` and calls `set_editmode_hooks(flush=convert.flush_edit_mesh)` (the omitted `enter`
reverts to the default, a no-op: the edit BMesh is born lazily in `from_edit_mesh`).
A `ModuleNotFoundError` whose `.name` is `"quartz.types"` or `"quartz.types.mesh"` is tolerated (installs
only the BVH adapter; missing sibling, §0.6); any other error propagates. Calling again reinstalls the same
function objects (idempotent; `convert.bvh_from_bmesh` and `convert.flush_edit_mesh` are module
functions, never new closures). What restores the defaults is `quartz.testing.isolated()` and
`quartz.compat.deactivate()` (§3.0.2, §3.1.1), never this module.

Full edit-mode flow (§2.1.9): `object.mode_set(mode="EDIT")` → `Object.q_set_mode` →
`Mesh.q_set_editmode(True)` (only marks; `enter` hook is a no-op); `from_edit_mesh(me)` creates the BMesh; user code edits; `update_edit_mesh(me)` or
`Object.update_from_editmode()` writes without leaving; `mode_set(mode="OBJECT")` → `flush` hook writes,
`q_edit_data = None`. Without `from_edit_mesh`, entering and leaving edit mode does not change the geometry.
Edits made through `mesh.vertices` during edit mode are overwritten by the BMesh on write
(the edit BMesh wins) **[I]**. The old BMesh stays alive and detached after leaving the mode
(Blender invalidates it; divergence) **[I]**: `is_wrapped` and `q_mesh` do not change, `free()` remains a no-op,
and editing it no longer affects the mesh. The same holds when the mesh clears `q_edit_data` on its own:
built-in operator via `edit_meshes` (§2.7.2) and `_q_state_set` of undo/`.qz` (§2.3.1); the next
`from_edit_mesh` rebuilds from the current geometry. `quartz.bmesh` does not take part in the
`.qz`/undo state (the edit BMesh is never serialized).

#### 3.3.2 `quartz/bmesh/types.py`

Exports exactly the 21 names of `extras.bmesh.types` from the dump **[O]**: `BMesh`, `BMVert`, `BMEdge`,
`BMFace`, `BMLoop`, `BMElemSeq`, `BMVertSeq`, `BMEdgeSeq`, `BMFaceSeq`, `BMLoopSeq`, `BMIter`,
`BMEditSelSeq`, `BMEditSelIter`, `BMLayerAccessVert`, `BMLayerAccessEdge`, `BMLayerAccessFace`,
`BMLayerAccessLoop`, `BMLayerCollection`, `BMLayerItem`, `BMLoopUV`, `BMDeformVert`. Each member listed
in the dump for a type MUST exist as a class attribute (`hasattr(cls, name)`); those marked NI
below raise `NotImplementedInQuartz(f"bmesh.types.{Type}.{member}")` when called.

```python
SELECT_MODES: tuple[str, ...] = ("VERT", "EDGE", "FACE")
TRANSFORM_FILTERS: tuple[str, ...] = ("SELECT", "HIDE", "SEAM", "SMOOTH", "TAG")
LAYER_KINDS: Mapping[str, tuple[str, ...]] = {              # attribute name of BMLayerAccess* -> [O] dump
    "VERT": ("bool", "color", "deform", "float", "float_color", "float_vector", "int", "shape", "skin", "string"),
    "EDGE": ("bool", "color", "float", "float_color", "float_vector", "int", "string"),
    "FACE": ("bool", "color", "float", "float_color", "float_vector", "int", "string"),
    "LOOP": ("bool", "color", "float", "float_color", "float_vector", "int", "string", "uv"),
}
class BMesh:
    def __init__(self) -> None                          # empty, unwrapped
    verts: "BMVertSeq"; edges: "BMEdgeSeq"; faces: "BMFaceSeq"; loops: "BMLoopSeq"   # ro, stable identity
    select_mode: set[str]                               # rw; default {"VERT"}; copy on read
    select_history: "BMEditSelSeq"                      # ro
    is_valid: bool                                      # ro; False after free() (does not raise)
    is_wrapped: bool                                    # ro; True only for the BMesh from from_edit_mesh
    uv_select_sync_valid: bool                          # rw; default False; only stored [I]
    q_mesh: "Mesh | None"                               # ro; the edit BMesh's mesh, otherwise None
    def from_mesh(self, mesh: "Mesh", face_normals: bool = True, vertex_normals: bool = True,
                  use_shape_key: bool = False, shape_key_index: int = 0) -> None   # -> convert.mesh_to_bmesh; use_shape_key=True -> NI; shape_key_index ignored
    def from_object(self, object: "Object", depsgraph: "Depsgraph", cage: bool = False,
                    face_normals: bool = True, vertex_normals: bool = True) -> None   # uses object.data (evaluated = original)
    def to_mesh(self, mesh: "Mesh") -> None             # -> convert.bmesh_to_mesh
    def free(self) -> None
    def clear(self) -> None
    def copy(self) -> "BMesh"
    def normal_update(self) -> None
    def calc_loop_triangles(self) -> list[tuple["BMLoop", "BMLoop", "BMLoop"]]
    def calc_volume(self, signed: bool = False) -> float
    def select_flush(self, select: bool) -> None
    def select_flush_mode(self) -> None
    def transform(self, matrix: "Matrix | Sequence", filter: set[str] | None = None) -> None
    def uv_select_flush(self, *a, **k) -> NoReturn; def uv_select_flush_mode(self, *a, **k) -> NoReturn
    def uv_select_flush_shared(self, *a, **k) -> NoReturn; def uv_select_foreach_set(self, *a, **k) -> NoReturn
    def uv_select_foreach_set_from_mesh(self, *a, **k) -> NoReturn; def uv_select_sync_from_mesh(self, *a, **k) -> NoReturn
    def uv_select_sync_to_mesh(self, *a, **k) -> NoReturn                                   # NI (all uv_select_* of BMesh)
    def __repr__(self) -> str      # live: contains "BMesh", f"totvert={V}", f"totedge={E}", f"totface={F}", f"totloop={L}"; dead: "<BMesh dead at 0x…>" [I]

class BMVert:                       # not directly instantiable: BMVert() -> PropertyTypeError "cannot create" [I]
    co: Vector; normal: Vector      # rw (wrapped, 3)
    select: bool; hide: bool; tag: bool; index: int     # rw (assigning select/hide changes only its own flag)
    is_valid: bool; is_boundary: bool; is_manifold: bool; is_wire: bool                   # ro
    link_edges: "BMElemSeq[BMEdge]"; link_faces: "BMElemSeq[BMFace]"; link_loops: "BMElemSeq[BMLoop]"   # ro
    def select_set(self, select: bool) -> None; def hide_set(self, hide: bool) -> None
    def normal_update(self) -> None
    def calc_edge_angle(self, fallback: object = None) -> float
    def calc_shell_factor(self) -> float
    def copy_from(self, other: "BMVert") -> None
    def copy_from_vert_interp(self, vert_pair, fac) -> NoReturn; def copy_from_face_interp(self, face) -> NoReturn   # NI
    def __getitem__(self, layer: "BMLayerItem") -> object; def __setitem__(self, layer: "BMLayerItem", value: object) -> None
class BMEdge:
    verts: "BMElemSeq[BMVert]"      # ro, 2 items, in creation order
    select: bool; hide: bool; tag: bool; seam: bool; smooth: bool; index: int             # rw
    is_valid: bool; is_boundary: bool; is_contiguous: bool; is_convex: bool; is_manifold: bool; is_wire: bool   # ro
    link_faces: "BMElemSeq[BMFace]"; link_loops: "BMElemSeq[BMLoop]"                      # ro
    def select_set(self, select: bool) -> None; def hide_set(self, hide: bool) -> None
    def other_vert(self, vert: BMVert) -> BMVert | None
    def calc_length(self) -> float
    def calc_face_angle(self, fallback: object = None) -> float
    def calc_face_angle_signed(self, fallback: object = None) -> float
    def calc_tangent(self, loop: "BMLoop") -> Vector
    def normal_update(self) -> None
    def copy_from(self, other: "BMEdge") -> None
    def __getitem__(self, layer) -> object; def __setitem__(self, layer, value) -> None
class BMFace:
    verts: "BMElemSeq[BMVert]"; edges: "BMElemSeq[BMEdge]"; loops: "BMElemSeq[BMLoop]"   # ro, loop order
    normal: Vector                  # rw (wrapped, 3)
    material_index: int; smooth: bool; select: bool; hide: bool; tag: bool; index: int; uv_select: bool   # rw
    is_valid: bool                  # ro
    def select_set(self, select: bool) -> None; def hide_set(self, hide: bool) -> None; def uv_select_set(self, select: bool) -> None
    def calc_area(self) -> float; def calc_perimeter(self) -> float
    def calc_center_median(self) -> Vector; def calc_center_median_weighted(self) -> Vector; def calc_center_bounds(self) -> Vector
    def calc_tangent_edge(self) -> Vector; def calc_tangent_edge_pair(self) -> Vector
    def calc_tangent_edge_diagonal(self) -> Vector; def calc_tangent_vert_diagonal(self) -> Vector
    def normal_update(self) -> None; def normal_flip(self) -> None
    def copy(self, verts: bool = True, edges: bool = True) -> "BMFace"
    def copy_from(self, other: "BMFace") -> None
    def copy_from_face_interp(self, face, vert: bool = True) -> NoReturn                  # NI
    def __getitem__(self, layer) -> object; def __setitem__(self, layer, value) -> None
class BMLoop:
    vert: BMVert; edge: BMEdge; face: BMFace; index: int                                   # ro (index rw)
    link_loop_next: "BMLoop"; link_loop_prev: "BMLoop"; link_loop_radial_next: "BMLoop"; link_loop_radial_prev: "BMLoop"
    link_loops: "BMElemSeq[BMLoop]" # ro: the other loops of the same vertex
    tag: bool; uv_select_vert: bool; uv_select_edge: bool                                  # rw
    is_valid: bool; is_convex: bool                                                        # ro
    def uv_select_vert_set(self, select: bool) -> None; def uv_select_edge_set(self, select: bool) -> None
    def calc_angle(self) -> float; def calc_normal(self) -> Vector; def calc_tangent(self) -> Vector
    def copy_from(self, other: "BMLoop") -> None
    def copy_from_face_interp(self, face, vert: bool = True, multires: bool = True) -> NoReturn   # NI
    def __getitem__(self, layer) -> object; def __setitem__(self, layer, value) -> None
class BMElemSeq:                    # ro view: face.verts, edge.link_faces, ...; len, iter, [int|slice], in
    def index_update(self) -> None  # index = position in this sequence
class BMVertSeq:
    layers: BMLayerAccessVert
    def new(self, co: Sequence[float] = (0.0, 0.0, 0.0), example: BMVert | None = None) -> BMVert
    def remove(self, vert: BMVert) -> None
    def ensure_lookup_table(self) -> None; def index_update(self) -> None
    def sort(self, key: Callable[[BMVert], object] | None = None, reverse: bool = False) -> None
    # __len__, __iter__ (-> BMIter), __getitem__(int|slice)
class BMEdgeSeq:                    # = BMVertSeq + :
    layers: BMLayerAccessEdge
    def new(self, verts: Sequence[BMVert], example: BMEdge | None = None) -> BMEdge
    def get(self, verts: Sequence[BMVert], fallback: object = None) -> BMEdge | object
class BMFaceSeq:                    # = BMVertSeq + :
    layers: BMLayerAccessFace
    active: BMFace | None           # rw
    def new(self, verts: Sequence[BMVert], example: BMFace | None = None) -> BMFace
    def get(self, verts: Sequence[BMVert], fallback: object = None) -> BMFace | object
class BMLoopSeq:
    layers: BMLayerAccessLoop       # only member; len()/iter -> PropertyTypeError with "loops" [I]
class BMIter:                       # iterator returned by iter() of the sequences (__iter__/__next__)
class BMEditSelSeq:
    active: BMVert | BMEdge | BMFace | None    # ro: last item
    def add(self, element) -> None; def remove(self, element) -> None; def discard(self, element) -> None
    def clear(self) -> None; def validate(self) -> None
    # __len__, __iter__ (-> BMEditSelIter), __getitem__(int), __contains__
class BMEditSelIter: ...
class BMLayerAccessVert: ...       # one BMLayerCollection attribute (ro, stable identity) per name in LAYER_KINDS["VERT"]
class BMLayerAccessEdge: ...       # same for LAYER_KINDS["EDGE"]
class BMLayerAccessFace: ...       # same for LAYER_KINDS["FACE"]
class BMLayerAccessLoop: ...       # same for LAYER_KINDS["LOOP"]
class BMLayerCollection:
    active: BMLayerItem | None; is_singleton: bool                                         # ro
    def new(self, name: str = "") -> BMLayerItem
    def remove(self, layer: BMLayerItem) -> None
    def verify(self) -> BMLayerItem
    def get(self, key: str, default: object = None) -> BMLayerItem | object
    def keys(self) -> list[str]; def values(self) -> list[BMLayerItem]; def items(self) -> list[tuple[str, BMLayerItem]]
    # __len__, __iter__ (layers), __getitem__(str|int), __contains__(str)
class BMLayerItem:
    name: str                       # ro
    def copy_from(self, other: "BMLayerItem") -> None
class BMLoopUV:                     # value of loop[uv_layer]; live view of the loop
    uv: Vector                      # rw (wrapped, 2)
    pin_uv: bool                    # rw
class BMDeformVert:                 # mapping group(int) -> weight(float); keys, values, items, get, clear, [ ], del, len
```

**Structure and links.**

1. Each `BMFace` has loops (`BMLoop`) in cyclic order; loop `i` links `verts[i]` to `verts[i+1]`
   through edge `edges[i]`. `link_loop_next/prev` circulate within the face. The radial cycle of an edge
   is the loops of all faces that use it, in creation order; `link_loop_radial_next/prev`
   circulate in it (single loop → itself) **[I]**.
2. `link_edges`, `link_faces`, `link_loops` of a vertex and `link_faces`, `link_loops` of an edge: link
   creation order **[I]**. `is_wire`: edge with no faces; vertex with edges and no faces
   (loose vertex → `False`) **[I]**. `is_boundary`: edge with exactly 1 face; vertex with
   some boundary edge. `is_manifold`: edge with exactly 2 faces; vertex whose edges are
   all manifold and whose faces form a single fan **[I]**. `BMEdge.is_contiguous`: manifold and
   the two faces traverse the edge in opposite directions. `is_convex` (edge): angle between faces
   convex; (loop): interior angle < π in the face plane **[I]**.
3. `BMEdge.other_vert(v)` → the other vertex; `v` not on the edge → `None` **[I]**.

**Creation and removal.**

1. `verts.new(co, example)`: `co` of 3 numbers (otherwise `PropertyValueError` with `"verts.new"`);
   `example` copies layer values and flags (`select`, `hide`, `tag`) **[I]**; `normal` zero.
2. `edges.new(verts, example)`: exactly 2 distinct vertices (otherwise `PropertyValueError` with
   `"edges.new"`); edge already existing between them → `PropertyValueError` with `"edge exists"` **[I]**;
   `verts` of the new edge in the given order.
3. `faces.new(verts, example)`: ≥ 3 vertices, no repetition (`PropertyValueError` with
   `"faces.new"`); face with the same vertex set already exists → `PropertyValueError` with
   `"face already exists"` **[I]**; missing edges are created (`verts` = (loop's vertex,
   next)); `normal` computed at creation; `example` copies `material_index`, `smooth` and
   face layer values (and loop layer values, position by position, if it has the same number of loops) **[I]**.
4. Element from another BMesh → `PropertyValueError` with `"another"`; dead element →
   `RemovedStructError`; wrong type → `PropertyTypeError` **[I]**.
5. `verts.remove(v)`: removes `v`, its edges, the faces that use those edges and their loops.
   `edges.remove(e)`: removes `e` and the faces that use it (vertices stay). `faces.remove(f)`: only the face
   and its loops **[I]**. Removed elements leave `select_history` and `faces.active`.
6. **Death**: a removed element (or one from a freed BMesh) switches class to a "dead" subclass
   cached per class (`__slots__ = ()`, class attribute `_q_removed = True`): `is_valid` →
   `False`; reading, writing or calling any other name without a leading `_` (and `elem[layer]`) →
   `RemovedStructError(f"BMesh data of type {Type} has been removed")` **[I]**; `_q_*` names remain
   accessible to the module itself;
   `repr` → `f"<{Type} dead at 0x…>"`; `hash`/identity preserved. A wrapped `Vector` of a
   dead element has `is_valid == False` (§1.4.1).
7. `free()`: unwrapped BMesh → kills the BMesh and all elements (same rule; `is_valid`
   remains readable); wrapped → no-op (the edit BMesh belongs to the mesh) **[I]**. `clear()`:
   kills all elements and removes all layers; the BMesh stays valid **[I]**.

**Indices and lookup table.**

1. A new element has `index == -1` **[I]**; `from_mesh` gives each element the mesh index
   (vertex, edge, face, loop); `index_update()` renumbers by position in the sequence; `to_mesh`
   renumbers everything like `index_update()` **[I]**; `index` is writable.
2. `seq[i]` (vertices, edges, faces) uses a table: valid after `ensure_lookup_table()` and on a
   freshly created empty BMesh (`BMesh()`/`new()`); invalid on the BMesh returned by `copy()` and on the one from
   `from_edit_mesh`; invalidated by `new`, `remove`, `sort`, `from_mesh`, `clear` and by any
   op/util that creates or removes elements of that type (`index_update()` does not validate it). Invalid table → `IndexError` with
   `"outdated internal index table, run ensure_lookup_table() first"` **[I]**; out of
   range → `IndexError` with `"out of range"`; negatives accepted; slice → `list`. `BMElemSeq` has no table.
3. `iter(seq)` walks a snapshot (removing during iteration does not skip items) **[I]**.
4. `sort(key=None, reverse=False)`: reorders the sequence (default key: `index`), renumbers `index`
   by the new order and invalidates the table **[I]**.

**Selection and visibility** (hidden elements are not affected by flush) **[I]**:

1. `elem.select = x` / `elem.hide = x` change only the element's own flag.
2. `select_set(True)`: vertex → itself; edge → itself and its 2 vertices; face → itself, its edges and
   vertices. `select_set(False)`: vertex → itself, its edges and faces; edge → itself, its faces, and
   each vertex that does not belong to another selected edge; face → itself, and each edge/vertex that does not
   belong to another selected face.
3. `hide_set(True)` also deselects: vertex → itself, edges and faces; edge → itself and faces;
   vertices only if all their edges end up hidden; face → itself; edges whose faces are
   all hidden; vertices whose edges are all hidden. `hide_set(False)`: the element and
   its subelements (face → edges and vertices; edge → vertices).
4. `select_flush(True)`: edge selected if both vertices are; face if all vertices are.
   `select_flush(False)`: edge/face with any unselected vertex is deselected.
5. `select_flush_mode()`: `"VERT"` in `select_mode` → like `select_flush(True)` and also
   deselects edges/faces with an unselected vertex; otherwise `"EDGE"` → face selected iff all
   edges are; otherwise `"FACE"` → edges and vertices selected iff they belong to a selected face.
6. `select_mode` accepts a non-empty set ⊆ `SELECT_MODES`; anything else → `PropertyValueError` with
   `"select_mode"` **[I]**.
7. `select_history`: ordered list without repetition. `add` (re)inserts at the end; `remove` of an absent item →
   `PropertyValueError`; `discard` silent; `validate()` removes dead or unselected items;
   `active` = last or `None`. An item that is not `BMVert`/`BMEdge`/`BMFace` → `PropertyTypeError`; from
   another BMesh → `PropertyValueError` with `"another"`; dead → `RemovedStructError`. `faces.active`
   accepts `None` or a live face of this BMesh (same errors).
8. `BMFace.uv_select_set`, `BMLoop.uv_select_vert_set`/`uv_select_edge_set` and the
   `uv_select*` attributes change only the element's own flag (no UV propagation; the `BMesh.uv_select_*` are NI) **[I]**.

**Calculations** (computations in float64; Newell and averages of §1.5.3) **[I]**:

1. `normal_update()` of the BMesh: normal of each face by normalized Newell (degenerate → zero); of
   each vertex, average of the face normals weighted by the loop angle, normalized (vertex
   without faces → normalized position). `BMFace.normal_update()` only the face; `BMVert.normal_update()`
   recomputes the vertex's faces and then the vertex; `BMEdge.normal_update()` does the same for its 2
   vertices. `normal_flip()` reverses the loop order keeping the 1st and negates the normal.
2. `calc_area` (Newell/2), `calc_perimeter`, `calc_center_median` (mean of the vertices),
   `calc_center_median_weighted` (mean weighted by the length of the edges adjacent to each
   vertex), `calc_center_bounds` (center of the box), `calc_tangent_edge` (normalized direction of the
   longest edge), `calc_tangent_edge_pair` (sum of the two longest opposite edges; triangle
   = `calc_tangent_edge`), `calc_tangent_edge_diagonal` (direction of the edge whose greatest distance to a
   vertex of the face is maximal), `calc_tangent_vert_diagonal` (direction between the two vertices
   farthest from each other). Tangents: normalized, oriented from the vertex with the lower loop position to
   the one with the higher; tie → the first candidate in loop order; degenerate face → zero vector.
   `calc_length` = distance between the 2 vertices.
3. `calc_face_angle(fallback)`: angle between the normals of the 2 faces; edge without exactly 2 faces →
   `fallback` if given, otherwise `PropertyValueError` with `"calc_face_angle"`; `_signed`: negative if
   concave. `calc_edge_angle(fallback)`: deviation between the vertex's 2 edges, `π − ∠(a, v, b)`
   (collinear → 0.0; right-angle bend → π/2); ≠ 2 edges → `fallback` or
   `PropertyValueError` with `"calc_edge_angle"`. `calc_shell_factor()`: mean of
   1/cos(angle between the vertex normal and that of each face), weighted by the vertex's loop angle
   in each face; 1.0 without faces.
   `BMEdge.calc_tangent(loop)`: vector in the plane of the loop's face, perpendicular to the edge, pointing
   inward. `BMLoop.calc_angle` (interior angle), `calc_normal` (normalized cross product of the loop's
   edges; collinear → face normal), `calc_tangent` (normalized interior bisector).
4. `calc_loop_triangles()`: faces in order; each face triangulated with the rule of §1.5.3 (quad by the
   shorter diagonal, n-gon by ear clipping in the face plane), keeping the winding; cube → 12
   tuples; default UV sphere → 960 **[I]**.
5. `calc_volume(signed=False)`: sum of the tetrahedra (origin, fan of each face) / 6; `signed=False`
   → absolute value. Cube of side 2 → 8.0 (with inverted normals and `signed=True` → −8.0).
6. `transform(matrix, filter=None)`: 4×4 `matrix` (3×3 is extended) applied to the vertices' `co`
   (with `w = 1`); `filter` ⊆ `TRANSFORM_FILTERS` → only vertices with any of the flags (`SEAM`/`SMOOTH`
   never match vertices); invalid item → `PropertyValueError`. Normals are not recomputed.
7. `copy()`: new unwrapped BMesh with elements, flags, indices, layers (names, order, values,
   active), `select_mode`, `select_history` and `faces.active` mapped. `copy_from(other)`: copies
   layer values (layers matched by name and type, including across BMeshes) and flags (`select`,
   `hide`, `tag`; edge `seam`/`smooth`; face `material_index`/`smooth`); a vertex also `co` and
   `normal`; a face also `normal` **[I]**. `BMFace.copy(verts=True, edges=True)`: new face with the
   same data; `verts=True` duplicates the vertices, `edges=True` duplicates the edges (otherwise reuses) **[I]**.

**Layers** (per-element values; type table in §3.3.3):

1. `seq.layers.<type>` is a `BMLayerCollection` (stable identity). `new(name="")`: empty name →
   per-type default (`uv` → `"UVMap"`, `float` → `"Float"`, `int` → `"Int"`, `bool` → `"Bool"`,
   `string` → `"String"`, `float_vector` → `"Vector"`, `float_color`/`color` → `"Color"`) **[I]**; the name
   is made unique among all layers of the BMesh (of all domains, including hidden ones) and the
   names consumed in §3.3.3, with `.001`, `.002`… (`quartz.types.naming` is not used: own
   rule, same form); initial values = `quartz.geometry.default_fill(T)` with `T` the corresponding
   attribute type (`float` → `FLOAT`, `int` → `INT`, `bool` → `BOOLEAN`, `float_vector` →
   `FLOAT_VECTOR`, `float_color` → `FLOAT_COLOR`, `color` → `BYTE_COLOR` divided by 255, `uv` →
   `FLOAT2`; zeros), `string` → `b""`. Non-`str` name → `PropertyTypeError`.
2. `elem[layer]`: `float` → `float`; `int` → `int`; `bool` → `bool`; `string` → `bytes`;
   `float_vector` → wrapped `Vector` (3); `float_color` and `color` → wrapped `Vector` (4)
   (`color` coming from `BYTE_COLOR` stays in [0, 1]; writing outside [0, 1] is accepted and clamped only
   when writing back, §3.3.3); `uv` → `BMLoopUV` (live view with `uv` and `pin_uv`). Assignment coerces (`float32`/`int32`,
   sequence of the right size; `string` accepts `bytes`/`str`); invalid value → `PropertyTypeError` or
   `PropertyValueError`; key that is not a `BMLayerItem` → `PropertyTypeError`; layer from another domain
   or another BMesh → `PropertyValueError` with `"layer"`; `del elem[layer]` → `PropertyTypeError`.
3. `active`: `uv` → the active UV (the mesh's in `from_mesh`; otherwise the first; removing the active one moves to the
   first remaining); others → the first layer or `None` **[I]**. `verify()` → `active`, creating
   `new()` if there is none. `is_singleton`: `True` only for `deform` and `skin` **[I]**. `remove(layer)`:
   removes the layer and its values; the `BMLayerItem` dies (death rule). `copy_from(other)`: same
   domain and type (otherwise `PropertyValueError`); copies the value of each element.
4. `deform`, `shape`, `skin` exist and stay empty: `new()`/`verify()` →
   `NotImplementedInQuartz(f"bmesh.types.BMLayerAccessVert.{type}")` (no group weights or shape
   keys in this milestone) **[I]**.

#### 3.3.3 `quartz/bmesh/convert.py`

```python
class MeshLike(Protocol):           # duck typing (Mesh of §2.3.1 or local test fake)
    q_geometry: MeshGeometry                             # required
    def q_set_geometry(self, geo: MeshGeometry) -> None  # required (adopts without copying and stamps "GEOMETRY")
    # optional: name: str (missing = ""); is_editmode: bool (missing = False); q_edit_data;
    # uv_layers: collection with .active (item with .name, or None), .get(name) and assignment of .active (UVLoopLayers of §2.3.1)
def mesh_to_bmesh(mesh: MeshLike, bm: "BMesh", *, face_normals: bool = True, vertex_normals: bool = True) -> None
    # = geometry_to_bmesh(mesh.q_geometry, bm, ..., active_uv=name of mesh.uv_layers.active if any)
def bmesh_to_mesh(bm: "BMesh", mesh: MeshLike) -> None
    # mesh.is_editmode -> PropertyValueError(f"to_mesh(): Mesh '{mesh.name}' is in editmode") [I];
    # mesh.q_set_geometry(bmesh_to_geometry(bm)); if bm has an active UV and mesh.uv_layers exists:
    # layer = mesh.uv_layers.get(name); layer not None -> mesh.uv_layers.active = layer
def geometry_to_bmesh(geo: MeshGeometry, bm: "BMesh", *, face_normals: bool = True, vertex_normals: bool = True,
                      active_uv: str | None = None) -> None          # appends (non-empty BMesh: merges) [I]
def bmesh_to_geometry(bm: "BMesh") -> MeshGeometry                   # new geometry, independent of the BMesh
def flush_edit_mesh(mesh: MeshLike) -> None
    # `flush` hook (§2.1.9): bm = mesh.q_edit_data; live BMesh -> mesh.q_set_geometry(bmesh_to_geometry(bm)) (+ active UV);
    # otherwise no-op; does NOT check is_editmode
def bvh_from_bmesh(bmesh: "BMesh", epsilon: float = 0.0) -> BVHTree
    # BVHTree.FromBMesh adapter, called as fn(bmesh, epsilon=epsilon) [I]
```

`BMesh.from_mesh(mesh, face_normals, vertex_normals, use_shape_key, shape_key_index)` = `mesh_to_bmesh`
(`use_shape_key=True` → `NotImplementedInQuartz("bmesh.types.BMesh.from_mesh", "use_shape_key=True")`;
no `q_geometry` → `PropertyTypeError` with `"expected a Mesh"`; dead BMesh → `RemovedStructError`).
`BMesh.to_mesh(mesh)` = `bmesh_to_mesh` (same two errors, checked before `is_editmode`). `BMesh.from_object(object, depsgraph, ...)` = `mesh_to_bmesh(object.data, ...)`;
`object.data` without `q_geometry` → `PropertyValueError` with `"has no mesh data"` **[I]**. Reading a mesh in
edit mode is allowed (it reads `q_geometry`).

**`geometry_to_bmesh`** (in order; nothing in `geo` is changed):

0. `geo` not a `MeshGeometry` → `PropertyTypeError` with `"MeshGeometry"`; dead `bm` →
   `RemovedStructError`; `geo.validate()` (without `fix`) with problems → `PropertyValueError` with
   `"invalid geometry"` and the 1st problem **[I]** (nothing is added to `bm`).
1. Internal construction, without the checks of `edges.new`/`faces.new` (faces with the same set
   of vertices are accepted, as they came): one `BMVert` per vertex (`co` = `positions[i]`), one
   `BMEdge` per row of `.edge_verts` (in row order), one `BMFace` per face with the corners from
   `face_offsets[k]` to `face_offsets[k+1]` (corner `face_offsets[k]` is the 1st); each corner uses the edge
   from `.corner_edge`. Indices = those of the geometry (added to the number of elements already existing
   when merging). `select_history` and `faces.active` do not change (the mesh stores no history or active
   face in Quartz; in a new BMesh they stay empty/`None`); `select_mode` does not change.
2. **Consumed** attributes (they become fields/flags, never layers), recognized only with the indicated domain and
   type; absent → default value:

| Attribute | Domain / type | Field | Default |
|---|---|---|---|
| `position`, `.edge_verts`, `.corner_vert`, `.corner_edge` **[The name]** | required | topology, `co` | — |
| `.select_vert` **[The name]** / `.hide_vert` | POINT / BOOLEAN | `BMVert.select` / `hide` | `False` |
| `.select_edge` **[The name]** / `.hide_edge` | EDGE / BOOLEAN | `BMEdge.select` / `hide` | `False` |
| `.uv_seam` | EDGE / BOOLEAN | `BMEdge.seam` | `False` |
| `sharp_edge` | EDGE / BOOLEAN | `BMEdge.smooth = not value` | `smooth = True` |
| `.select_poly` **[The name]** / `.hide_poly` | FACE / BOOLEAN | `BMFace.select` / `hide` | `False` |
| `sharp_face` **[The name]** | FACE / BOOLEAN | `BMFace.smooth = not value` | `smooth = True` |
| `material_index` | FACE / INT | `BMFace.material_index` | `0` |
| `.uv_select_face` **[The name]** | FACE / BOOLEAN | `BMFace.uv_select` | `False` |
| `.uv_select_vert` / `.uv_select_edge` **[The name]** | CORNER / BOOLEAN | `BMLoop.uv_select_vert` / `uv_select_edge` | `False` |
| `f".pn.{uv}"` for each UV layer `uv` of this conversion | CORNER / BOOLEAN | `BMLoopUV.pin_uv` | `False` |

   (Names marked **[O]** = present in the factory Cube of the dump, `factory_scene.meshes`; the other names
   are **[I]**. `f".pn.{X}"` is only consumed if `X` becomes a `uv` layer in step 3; otherwise it is hidden.)
3. Other attributes, decided in this order: (a) name with a leading `.` → **hidden** layer; (b) type
   with no layer type (`INT8`, `INT16_2D`, `INT32_2D`, `FLOAT2` outside CORNER, `QUATERNION`,
   `FLOAT4X4`) → **hidden** layer; (c) otherwise, visible layer of the domain (POINT → `verts`, EDGE →
   `edges`, FACE → `faces`, CORNER → `loops`) by type: `FLOAT` → `float`; `INT` → `int`; `BOOLEAN`
   → `bool`; `FLOAT_VECTOR` → `float_vector`; `FLOAT_COLOR` → `float_color`; `BYTE_COLOR` → `color`
   (value/255 in `float32`); `FLOAT2` in CORNER → `uv`. Hidden layers keep the `data_type` and the
   original per-element array (invisible in `layers`, copied by `copy`/`copy_from`/ops,
   written back) — the round trip loses no attribute **[I]**. When merging into a BMesh that already
   has a layer with the same name, domain and type, it is reused; same name with another domain/type → name
   made unique **[I]**. Already existing elements receive `default_fill` in the new layers, and the
   new ones receive `default_fill` in the layers that the geometry does not bring.
4. The order of the non-required attributes of the geometry is recorded in the BMesh (to write back in the same
   order; when merging, names not yet recorded go at the end in the order of `geo`) and the set of
   consumed attributes present is also recorded.
5. `face_normals` → `BMFace.normal` = `quartz.geometry.face_normals(geo)`; `vertex_normals` →
   `BMVert.normal` = `quartz.geometry.vertex_normals(geo)`; false → zeros. Existing `active_uv` →
   active UV layer.
6. Invalidates the lookup tables of the 3 sequences.

**`bmesh_to_geometry`** (in order):

1. Vertices, edges and faces in the iteration order of the sequences; corners of each face starting from
   `face.loops[0]`; `.corner_edge` = output index of each corner's edge. Declared side effect:
   each element (including corners) receives `index` = output position (like
   `index_update()`); the lookup tables are not invalidated (the order does not change). Dead BMesh →
   `RemovedStructError`.
2. Non-required attributes in the recorded order; then, consumed ones that were not in the source but
   now need to be written (in table order); then, layers created after the conversion (in
   creation order). A consumed attribute is written if it was present in the source **or** if some
   element has a value different from the table default; if its name is taken by a layer
   (visible or hidden) of another domain/type, the layer wins and the field is not written **[I]**.
   `BYTE_COLOR` = `round(value·255)` clamped to [0, 255]; `string` layers are not written (there is no
   text attribute type) **[I]**.
3. Round-trip property (tested): for every valid geometry `g`,
   `bmesh_to_geometry(b)` with `b` coming from `geometry_to_bmesh(g, BMesh())` without editing has the same
   `face_offsets`, the same required arrays and the same set of attributes (name, domain, type,
   identical values, bit for bit), in the same order for the non-required ones.

**`bvh_from_bmesh(bmesh, epsilon)`**: dead BMesh → `RemovedStructError`; other type →
`PropertyTypeError`. Positions = `co` of the vertices in iteration order; triangles =
`calc_loop_triangles()` (vertex indices by iteration position); `tri_polygon` = position of the face
in `bm.faces`; returns `BVHTree._q_from_triangles(positions, tris, tri_polygon, epsilon)` (§1.4.9).
It does NOT change the `index` of any element.

#### 3.3.4 `quartz/bmesh/ops.py`

Exports the 83 names of `extras.bmesh.ops` from the dump **[O]** (`__all__` in alphabetical order). Implemented
(23): `create_cube`, `create_grid`, `create_circle`, `create_cone`, `create_uvsphere`,
`create_icosphere`, `triangulate`, `remove_doubles`, `find_doubles`, `recalc_face_normals`,
`reverse_faces`, `delete`, `duplicate`, `translate`, `rotate`, `scale`, `transform`,
`extrude_face_region`, `extrude_edge_only`, `extrude_vert_indiv`, `dissolve_verts`,
`dissolve_edges`, `dissolve_faces`. The other 60 are functions `def name(bm, /, **kwargs) -> NoReturn`
that raise `NotImplementedInQuartz(f"bmesh.ops.{name}")` without validating arguments (among them
`bmesh.ops.mesh_to_bmesh`, `bmesh_to_mesh` and `object_load_bmesh`, which are not the functions of
`quartz.bmesh.convert`). The parameter names below are those of the operator slots in Blender
**[I]** (the dump does not include them).

```python
M = "Matrix | Sequence[Sequence[float]]"      # 4x4 (extended 3x3); default = identity
def create_cube(bm, /, *, size: float = 0.0, matrix: M = None, calc_uvs: bool = False) -> dict          # {"verts"}
def create_grid(bm, /, *, x_segments: int = 0, y_segments: int = 0, size: float = 0.0, matrix: M = None, calc_uvs: bool = False) -> dict   # {"verts"}
def create_circle(bm, /, *, cap_ends: bool = False, cap_tris: bool = False, segments: int = 0, radius: float = 0.0,
                  matrix: M = None, calc_uvs: bool = False) -> dict                                       # {"verts"}
def create_cone(bm, /, *, cap_ends: bool = False, cap_tris: bool = False, segments: int = 0, radius1: float = 0.0,
                radius2: float = 0.0, depth: float = 0.0, matrix: M = None, calc_uvs: bool = False) -> dict  # {"verts"}
def create_uvsphere(bm, /, *, u_segments: int = 0, v_segments: int = 0, radius: float = 0.0, matrix: M = None, calc_uvs: bool = False) -> dict  # {"verts"}
def create_icosphere(bm, /, *, subdivisions: int = 0, radius: float = 0.0, matrix: M = None, calc_uvs: bool = False) -> dict   # {"verts"}
def triangulate(bm, /, *, faces=(), quad_method: str | int = "BEAUTY", ngon_method: str | int = "BEAUTY") -> dict
    # {"edges", "faces", "face_map", "face_map_double"}
def remove_doubles(bm, /, *, verts=(), dist: float = 0.0) -> dict                                        # {}
def find_doubles(bm, /, *, verts=(), keep_verts=(), dist: float = 0.0) -> dict                           # {"targetmap"}
def recalc_face_normals(bm, /, *, faces=()) -> dict                                                      # {}
def reverse_faces(bm, /, *, faces=(), flip_multires: bool = False) -> dict                               # {}
def delete(bm, /, *, geom=(), context: str | int = "VERTS") -> dict                                      # {}
def duplicate(bm, /, *, geom=(), dest: "BMesh | None" = None, use_select_history: bool = False,
              use_edge_flip_from_face: bool = False) -> dict
    # {"geom_orig", "geom", "vert_map", "edge_map", "face_map", "boundary_map", "isovert_map"}
def translate(bm, /, *, vec=(0.0, 0.0, 0.0), space: M = None, verts=(), use_shapekey: bool = False) -> dict          # {}
def rotate(bm, /, *, cent=(0.0, 0.0, 0.0), matrix: M = None, verts=(), space: M = None, use_shapekey: bool = False) -> dict   # {}
def scale(bm, /, *, vec=(0.0, 0.0, 0.0), space: M = None, verts=(), use_shapekey: bool = False) -> dict              # {}
def transform(bm, /, *, matrix: M = None, space: M = None, verts=(), use_shapekey: bool = False) -> dict             # {}
def extrude_face_region(bm, /, *, geom=(), edges_exclude=(), use_keep_orig: bool = False, use_normal_flip: bool = False,
                        use_normal_from_adjacent: bool = False, use_dissolve_ortho_edges: bool = False,
                        use_select_history: bool = False, skip_input_flip: bool = False) -> dict                 # {"geom"}
def extrude_edge_only(bm, /, *, edges=(), use_normal_flip: bool = False, use_select_history: bool = False) -> dict   # {"geom"}
def extrude_vert_indiv(bm, /, *, verts=(), use_select_history: bool = False) -> dict                         # {"edges", "verts"}
def dissolve_verts(bm, /, *, verts=(), use_face_split: bool = False, use_boundary_tear: bool = False) -> dict   # {}
def dissolve_edges(bm, /, *, edges=(), use_verts: bool = False, use_face_split: bool = False) -> dict          # {"region"}
def dissolve_faces(bm, /, *, faces=(), use_verts: bool = False) -> dict                                     # {"region"}
```

**Common protocol** (all ops):

1. Only `bm` is positional; other arguments are keyword-only (extra positional or unknown kwarg
   → Python's own `TypeError`). `bm` that is not a `BMesh` → `PropertyTypeError` with
   `"expected a BMesh"`; dead → `RemovedStructError`.
2. **Defaults**: an omitted parameter takes the operator slot's "zero" — `0`, `0.0`, `False`, empty
   list, identity matrix, first enum item **[I]** (the dump does not include defaults; a golden may
   correct this). Hence `create_cube(bm)` creates a cube of side 0.
3. Element arguments accept any iterable (including the sequences of `bm`); repeated ones
   count once; element of a type not accepted by the slot (`geom` accepts all three) →
   `PropertyTypeError` with the slot name; from another BMesh → `PropertyValueError` with `"another"`;
   dead → `RemovedStructError`.
4. Enums accept the identifier (`str`) or the Blender numeric value (`int`) **[I]**: in
   `triangulate`, the 0-based position in the given list (`quad_method` 0–4, `ngon_method` 0–1); in
   `delete`, the 1-based position (`"VERTS"` = 1 … `"TAGGED_ONLY"` = 7). Otherwise →
   `PropertyValueError` with the value; other type (`bool` included) → `PropertyTypeError`.
5. Return: new `dict`; `list` lists (never live sequences); `dict` maps.
6. Created elements copy flags and layer values from the source element (copy, extrusion,
   triangle) **[I]**; those created from scratch (`create_*`) use defaults. Ops do not flush selection,
   do not recompute normals of non-created elements (except `recalc_face_normals`/`reverse_faces`) and
   invalidate the affected lookup tables; a created element has `index == -1`.
7. `use_shapekey=True` → `NotImplementedInQuartz(f"bmesh.ops.{name}", "use_shapekey=True")`; likewise
   (op symbol, `f"{parameter}={value!r}"` in `detail`) for each unsupported parameter indicated
   below, checked before any change to `bm`.

**`create_*`**: build the geometry with `quartz.geometry.primitives` (§1.5.4), apply `matrix` to the
positions (`transform_points`) and add vertices, edges and faces to `bm` (`smooth = False`, like
the primitives' `sharp_face`); they do NOT create layers. With `calc_uvs` and an active UV layer, the primitive's UVs
go into it; without a UV layer, `calc_uvs` does nothing **[I]** (the primitive is always called
with `calc_uvs=calc_uvs`, and its `"UVMap"` attribute never becomes a layer). Return `{"verts": new
vertices in order}`. A `ValueError` from the primitive becomes `PropertyValueError` with `f"bmesh.ops.{op}"`.
`size`/`radius` equal to 0 (the default) is handled by calling the primitive with 1.0 and multiplying the
positions by 0 (degenerate result at the origin point of `matrix`), without depending on the primitive
accepting 0. Mapping **[I]**:

| Op | Primitive | Conversion | Minimum (otherwise `PropertyValueError` with `f"bmesh.ops.{op}"`) |
|---|---|---|---|
| `create_cube` | `cube(size=size)` | `size` = edge | — |
| `create_grid` | `grid(x_subdivisions=x_segments, y_subdivisions=y_segments, size=2*size)` | `size` = half width | segments ≥ 1 |
| `create_circle` | `circle(vertices=segments, radius=radius, fill_type=F)` | `F` = `"NOTHING"` without `cap_ends`; `"TRIFAN"` with `cap_ends` and `cap_tris`; otherwise `"NGON"` | `segments` ≥ 3 |
| `create_cone` | `cone(vertices=segments, radius1=radius1, radius2=radius2, depth=depth, end_fill_type=F)` | `F` as above; `depth` = total height | `segments` ≥ 3 |
| `create_uvsphere` | `uv_sphere(segments=u_segments, ring_count=v_segments, radius=radius)` | — | `u_segments` ≥ 3, `v_segments` ≥ 3 |
| `create_icosphere` | `ico_sphere(subdivisions=subdivisions, radius=radius)` | — | `subdivisions` ≥ 1 |

Resulting counts = those of §1.5.4 (e.g. `create_grid(x_segments=10, y_segments=10, size=1.0)` →
121 v / 100 f, box ±1 in XY; `create_uvsphere(u_segments=32, v_segments=16, radius=1.0)` → 482 v /
992 e / 512 f).

**`triangulate`**: each face in `faces` with more than 3 corners becomes triangles with the same vertices and
new edges on the diagonals. `quad_method` ∈ (`"BEAUTY"`, `"FIXED"`, `"ALTERNATE"`, `"SHORT_EDGE"`,
`"LONG_EDGE"`): `BEAUTY`/`SHORT_EDGE` → shortest diagonal (tie: the one from the 1st corner) (`BEAUTY` without
Blender's angle criterion: divergence **[I]**); `FIXED` → corners 0–2; `ALTERNATE` → 1–3;
`LONG_EDGE` → longest. `ngon_method` ∈ (`"BEAUTY"`, `"EAR_CLIP"`): both ear clipping in the face
plane **[I]**. The 1st triangle reuses the original `BMFace` object (corners rebuilt); the others are new;
all inherit `material_index`, `smooth`, flags and face layers, and each corner inherits the values of the original
corner at the same vertex. Return: `"faces"` = all resulting triangles (including the reused one),
`"edges"` = new diagonals, `"face_map"` = `{triangle: original face}` for each one, `"face_map_double"`
= `{}` **[I]**. Cube → 12 faces, 18 edges.

**`find_doubles` / `remove_doubles`** **[I]**: deterministic greedy grouping. Candidate list =
`keep_verts` (in the given order) followed by `verts` (in the given order, without those already in
`keep_verts`). Walking the list, each still-free candidate becomes a target and captures all free
candidates **coming from `verts`** at distance ≤ `dist` (Euclidean in `float64` over the `float32` `co`);
those captured stop being free; vertices of `keep_verts` are never captured.
`find_doubles` returns `{"targetmap": {captured: target}}` (insertion in list order) without changing
`bm`. `remove_doubles` (candidates = `verts`, without `keep_verts`): welds each vertex into its target (edges and corners move to the target), removes
degenerate and repeated edges (keeps the first), collapses consecutive repeated corners, removes faces with
fewer than 3 distinct vertices and repeated faces (same set of vertices; keeps the first).

**`recalc_face_normals`** **[I]**: per connected component (faces in `faces` linked by manifold
edges): consistent winding by breadth-first search from the component's 1st face (a neighbor that
traverses the edge in the same direction is flipped); then, with `S = Σ area·(normal · (center − centroid
of the component))` (center = `calc_center_median`; centroid = mean of the positions of the component's vertices,
each vertex once), `S < 0` flips the whole component; recomputes the normals
of those faces. Components in order of the 1st face in `faces`; faces outside `faces` do not change. **`reverse_faces`**:
`normal_flip()` on each face (1st corner kept; corner values follow their vertices).

**`delete`**: `context` ∈ (`"VERTS"`, `"EDGES"`, `"FACES_ONLY"`, `"EDGES_FACES"`, `"FACES"`,
`"FACES_KEEP_BOUNDARY"`, `"TAGGED_ONLY"`) **[I]**: `VERTS` → `verts.remove` of each vertex in `geom`;
`EDGES` → removes the edges (and their faces) and then their vertices left with no edges;
`FACES_ONLY` → only the faces; `EDGES_FACES` → the edges (and their faces) and the faces; `FACES` and
`FACES_KEEP_BOUNDARY` → the faces, then their edges with no remaining faces, then their vertices
with no remaining edges; `TAGGED_ONLY` → `NotImplementedInQuartz("bmesh.ops.delete", "context='TAGGED_ONLY'")`.
Elements of `geom` of a type the context does not use are ignored.

**`duplicate`**: copies the faces of `geom`, the edges of `geom` and of the faces, and the vertices of `geom`,
of the edges and of the faces (same coordinates, flags and layers); `dest` not `None` and different from `bm`
→ `NotImplementedInQuartz("bmesh.ops.duplicate", "dest=<other BMesh>")`; `use_edge_flip_from_face`
is accepted and ignored **[I]**. Return: `"geom_orig"` = input
(vertices, edges, faces), `"geom"` = new ones (vertices, edges, faces, in that order), `"vert_map"`/
`"edge_map"`/`"face_map"` = `{original: new}`, `"boundary_map"` = `{}`, `"isovert_map"` =
`{original: new}` of the vertices copied without a copied edge **[I]**. With `use_select_history`, the new ones
corresponding to the items of `select_history` are appended to it.

**`translate` / `rotate` / `scale` / `transform`** (only the vertices in `verts`; `S` = `space`): `co' =
S⁻¹·(S·co + vec)`; `co' = S⁻¹·(cent + R·(S·co − cent))` with `R` = `matrix` (4×4, applied to a
point); `co' = S⁻¹·(vec ⊙ (S·co))`; `co' = S⁻¹·M·S·co` **[I]**. Singular `S` → `PropertyValueError`.

**Extrusions** **[I]** (new coordinates = the original ones; the caller moves the result):

1. `extrude_face_region`: `F` = faces of `geom`; edges of `geom` outside the faces of `F` → as
   `extrude_edge_only`; vertices of `geom` outside them → as `extrude_vert_indiv`. For `F`: one new vertex
   per vertex of `F`; one new face per face of `F` (same winding, over the new ones); for each
   boundary edge of the region (used by exactly 1 face of `F`), traversed `a → b` in its face, one
   vertical edge per vertex and one side quad `(a, b, b', a')`. Fate of the original faces of
   `F`: with `use_keep_orig` → they stay as they are; otherwise, if some boundary edge of the region is also
   used by a face outside `F` → the faces of `F` are removed and then their edges and vertices
   left with no face and not on the boundary (region interior); otherwise (**isolated** region) → the faces of
   `F` stay and are flipped (`normal_flip`), closing the solid, except with `skip_input_flip`
   (they stay unflipped). `use_normal_flip` flips the new faces (top and sides). Return
   `{"geom": new vertices + new edges + new faces}` (in that order; kept original faces
   are not included). Isolated quad: 8 v / 12 e / 6 f, with the original face flipped (with
   `use_keep_orig` or `skip_input_flip`: same count, without flipping); top face of a cube:
   12 v / 20 e / 10 f. Non-empty `edges_exclude`, or true `use_normal_from_adjacent` or
   `use_dissolve_ortho_edges` → NI.
2. `extrude_edge_only`: one new vertex per vertex of the edges (shared among them); for each
   edge `(a, b)`: edge `(a', b')`, vertical edges and a quad — `(b, a, a', b')` if the edge has
   exactly one face that traverses it `a → b`, otherwise `(a, b, b', a')`; `use_normal_flip` flips.
   Return `{"geom": [...]}` as above. One loose edge: 4 v / 4 e / 1 f.
3. `extrude_vert_indiv`: for each vertex `v`, a new vertex `v'` and the edge `(v, v')`. Return
   `{"verts": [...], "edges": [...]}`.

**Dissolves** **[I]** (`use_face_split=True` → NI; the resulting face inherits data from the first face
involved, in the order of `link_faces`/input; every face resulting from a merge is a new `BMFace` object,
with `index == -1`, and the merged faces die; the 1st corner of the new face is that of the 1st vertex of the
new boundary found when walking the corners of the first involved face from `loops[0]`;
the winding is that of that face). **Bridge collapse** of a vertex `v` with exactly 2
edges `(u, v)` and `(v, w)`: the two become one edge `(u, w)` (if `(u, w)` already exists, the existing one is
kept and the two disappear), `v` leaves the cycle of each face that uses it (corners of `v` removed), faces
left with < 3 vertices are removed and `v` is removed.

1. `dissolve_verts`: for each live vertex of `verts`: with faces and not on the boundary → the faces of the
   fan become one face (the outer boundary of the fan), the vertex and its edges disappear; with faces and on the boundary →
   `use_boundary_tear` removes the vertex and its faces; otherwise the faces of the fan become one face whose
   boundary directly links the two boundary neighbors (result with < 3 vertices → faces removed);
   without faces and with exactly 2 edges → bridge collapse; others → the vertex is removed with its
   edges. 2×2 grid (9 v / 12 e / 4 f), center vertex → 8 v / 8 e / 1 f (octagon).
2. `dissolve_edges`: live edge with exactly 2 distinct faces → the two faces become one (the edge
   disappears); edge without faces → removed (vertices stay); others ignored. `use_verts` → then, each
   live vertex of the input edges left with exactly 2 edges undergoes bridge collapse.
   Return `{"region": faces resulting from the merges}`. 2×2 grid, one interior edge → 9 v / 11 e / 3 f
   (with `use_verts`: 8 v / 10 e / 3 f).
3. `dissolve_faces`: the faces are grouped into regions linked by edges; each region whose boundary is
   a single loop becomes one face (interior edges and vertices disappear); a region with more than one boundary
   loop stays intact. `use_verts` → vertices of the new boundary that did **not** have exactly 2
   edges before the dissolve and are left with exactly 2 undergo bridge collapse (grid corners,
   which already had 2, stay). Return `{"region": new faces}`. Entire 2×2 grid → 8 v / 8 e / 1 f (with
   `use_verts`: 4 v / 4 e / 1 f).

#### 3.3.5 `quartz/bmesh/utils.py` and `quartz/bmesh/geometry.py`

```python
# utils.py — exports the 14 names of extras.bmesh.utils [O]
def face_flip(faces: "BMFace") -> None                     # (the parameter is called faces and receives ONE face) = faces.normal_flip()
def vert_dissolve(vert: "BMVert") -> bool                  # dissolve_verts rule for one vertex; True if removed
def edge_split(edge: "BMEdge", vert: "BMVert", fac: float) -> tuple["BMEdge", "BMVert"]
def face_split(face: "BMFace", vert_a: "BMVert", vert_b: "BMVert", coords: Sequence = (), use_exist: bool = True,
               example: "BMEdge | None" = None) -> tuple["BMFace", "BMLoop"]
# edge_rotate, face_join, face_split_edgenet, face_vert_separate, loop_separate, uv_select_check, vert_collapse_edge,
# vert_collapse_faces, vert_separate, vert_splice -> def name(*args, **kwargs) -> NoReturn: NotImplementedInQuartz(f"bmesh.utils.{name}")
# geometry.py — exports the only name of extras.bmesh.geometry [O]
def intersect_face_point(face: "BMFace", point: Sequence[float]) -> bool
```

1. `edge_split(edge, vert, fac)`: `vert` outside the edge → `PropertyValueError` with `"edge_split"`;
   new vertex at `vert.co + fac·(other.co − vert.co)` (copies flags and layers from `vert`); the
   original edge now connects `vert` to the new one; returns `(new edge between the new vertex and the other vertex, new
   vertex)`; each face that used the edge gains a corner at the new vertex (corner values copied from the
   corner of `vert`) **[I]**.
2. `face_split(face, vert_a, vert_b, coords, use_exist, example)`: both vertices MUST belong to the face
   and not be adjacent in it (otherwise `PropertyValueError` with `"face_split"`); non-empty `coords` →
   `NotImplementedInQuartz("bmesh.utils.face_split", "coords")`. Creates the edge `vert_a–vert_b` (or
   reuses the existing one with `use_exist`; `example` copies flags/layers to it), keeps in `face` the
   corners from `vert_a` to `vert_b` and creates a new face with those from `vert_b` to `vert_a`; returns
   `(new face, corner of the new face whose edge is the new one)` **[I]**.
3. `intersect_face_point(face, point)`: projects `point` onto the face plane along the normal and returns
   whether it falls inside the polygon (the border counts as inside) **[I]**.

#### 3.3.6 `compat/bmesh/**`

Files: `compat/bmesh/__init__.py`, `types.py`, `ops.py`, `utils.py`, `geometry.py`. Only stdlib and
`quartz.*` (never numpy, §0.5); they only re-export (§3.0.1, thinness rule).

1. `bmesh/__init__.py`: `from quartz.bmesh import new, from_edit_mesh, update_edit_mesh`; imports the
   shim submodules (`from . import types, ops, utils, geometry`), which remain as attributes and in
   `sys.modules` as `bmesh.types` etc. (shim modules, not the module objects of `quartz.bmesh`);
   `__all__` = the 7 names of `extras.bmesh.__module__` **[O]** (`from_edit_mesh`, `geometry`, `new`,
   `ops`, `types`, `update_edit_mesh`, `utils`); finally `quartz.bmesh.install_adapters()` (the only
   import effect allowed, §3.0.2). `install_adapters` is not exported.
2. `types.py`, `ops.py`, `utils.py`, `geometry.py`: `from quartz.bmesh.<same> import <dump names>`
   and `__all__` with those names. Identity: `bmesh.types.BMesh is quartz.bmesh.types.BMesh`,
   `bmesh.ops.triangulate is quartz.bmesh.ops.triangulate`, `bmesh.new is quartz.bmesh.new` **[O
   names]**. No `q_`/`_q_` name nor `convert` appears in the shim.
3. `quartz.compat.deactivate()` removes `bmesh*` from `sys.modules` and returns the adapters (§3.1.1,
   steps 4 and 5 of deactivation); re-importing the shim after a new activation reinstalls them.

#### 3.3.7 Tests

Tests in `tests/bmesh/` that do not touch the session or hooks run without a fixture (only L1 +
`quartz.bmesh`, isolated); those that call `install_adapters`, use a real `Mesh` or the session MUST use
`qz`/`qz_empty` (the output of `quartz.testing.isolated` returns adapters and hooks, §2.6.8). Those that
depend on `l2-datablocks`/`l2-runtime`/`l2-operators`/`l3-compat-bpy` pass at the L3 gate (§0.6);
the rest MUST pass with only L1 and this task. Test meshes are built by the test itself
(`quartz.bmesh.ops.create_*`, `quartz.geometry.primitives`, `MeshGeometry.from_pydata`).

"No fixture" below = no session and no hooks; the read fixture `blender_dump` (§1.1.2) MAY
be used.

- `tests/bmesh/test_bmesh_types.py` (no fixture): `__all__`/`hasattr` of each member of the 21 types in the
  dump (`blender_dump["extras"]["bmesh"]["types"]`); `BMVert()` → `TypeError` with `"cannot create"`;
  unknown attribute → `AttributeError`; `verts.new`/`edges.new`/`faces.new` (implicit edges,
  order of `verts`, `"edge exists"`, `"face already exists"`, repetition, `"another"`); links
  (`link_*`, radial cycle, `link_loop_next/prev`, `other_vert` → `None`); `is_boundary`/`is_manifold`/
  `is_wire` on a quad, on a cube and on a loose edge; cascading removal (vertex/edge/face) and death
  rule (`is_valid`, `"has been removed"`, `repr` with `"dead"`, wrapped `Vector` with
  `is_valid == False`); `free()` (BMesh and dead elements), `clear()`; indices (`-1` on new ones,
  `index_update`, `sort` with `key`/`reverse`), table (`"outdated internal index table"` after `new` and
  after `from_mesh`, `ensure_lookup_table`, negatives, slice, `"out of range"`); iteration over a
  snapshot; `co` float32 (`0.1` → `0.10000000149011612`) and writing via `v.co.x += 1`; calculations
  (`calc_area` of the unit quad = 1, `calc_perimeter`, centers, `calc_length`, `calc_face_angle` of a
  cube edge = π/2 and `"calc_face_angle"`/`fallback`, `calc_edge_angle` (2 collinear edges →
  0.0, at a right angle → π/2, 3 edges → `"calc_edge_angle"`/`fallback`), `calc_loop_triangles`
  12 on the cube, `calc_volume` 8.0 and −8.0 with inverted normals, `normal_update` with outward normals,
  `transform` with and without `filter`, `normal_flip` keeping the 1st corner); `copy()` independent and with
  mapping of `select_history`/`faces.active`; `BMFace.copy`; `copy_from`; `repr` with `"totvert="`;
  `uv_select_*` of BMesh → NI; elements as `dict` keys (identity hash); `Vector` of
  `v.co` obtained before 100 `verts.new` still writes to the vertex; `v.co = (1, 2)` →
  `ValueError` with `"co"`.
- `tests/bmesh/test_bmesh_layers.py` (no fixture): `LAYER_KINDS` = dump members;
  `new` with default names and `.001` suffix; value types of `elem[layer]` (float32, int, bool, bytes,
  wrapped `Vector` 3/4, `BMLoopUV.uv`/`pin_uv`), coercion and errors (`"layer"`, non-layer key,
  `del`); `active`/`verify`/`remove`/`get`/`keys`/`is_singleton`; layer `copy_from`; `deform`/
  `shape`/`skin` → NI; selection (`select` only the flag, `select_set` ↑↓, `hide_set`, `select_flush(True/
  False)`, `select_flush_mode` in the 3 modes, invalid `select_mode` → `ValueError` with `"select_mode"`);
  `select_history` (`add`, `remove` of an absent item → `ValueError`, `discard`, `validate`, `active`).
- `tests/bmesh/test_bmesh_ops.py` (no fixture): `__all__` == the 83 names of the dump; each of the 60 not
  implemented → `NotImplementedInQuartz` with `f"bmesh.ops.{name}"` and has `_q_phantom is True`
  (the 23 implemented ones do not); protocol (extra positional and
  unknown kwarg → `TypeError`, wrong `bm` → `"expected a BMesh"`, slot with wrong type, invalid
  enum, enum `int` accepted, return with new lists); each `create_*` with the counts and boxes
  of §1.5.4, minimums (`ValueError`), `matrix` (translated box), `calc_uvs` with and without a UV layer;
  `triangulate` (cube → 12 f / 18 e; `FIXED` → edge between `verts[0]` and `verts[2]`; reuse of the
  original object; return keys; inherited face attributes); `find_doubles` without changes and with
  `keep_verts` as the preferred target (never a key of the `targetmap`); `remove_doubles`
  after `duplicate` of a cube → 8 v / 12 e / 6 f; `recalc_face_normals` with 3 inverted cube faces
  → all outward; `reverse_faces`; `delete` in the contexts with the 2×2 grid (VERTS center → 8/8/0;
  FACES at a corner → 8 v / 10 e / 3 f; FACES_ONLY → 9/12/3; inner EDGES → 9/11/2) and `TAGGED_ONLY` →
  NI (`str` contains `"bmesh.ops.delete"` and `"TAGGED_ONLY"`), `context=1` ≡ `"VERTS"`, `context=0` →
  `ValueError`; `duplicate` (doubled counts, maps, `dest` → NI); `translate`/`rotate`/`scale`/`transform`
  with and without `space`, `use_shapekey` → NI; the three extrusions with the counts of §3.3.4 (isolated quad:
  6 f and the original face normal negated; with `skip_input_flip` not negated; top of the cube: original
  face dead) and NI flags; the three dissolves with the counts of §3.3.4 (faces of `"region"` new, the
  joined ones dead) and `use_face_split` → NI.
- `tests/bmesh/test_bmesh_utils_geometry.py` (no fixture): `__all__` of `utils` (14) and `geometry` (1)
  == dump; 10 utils NI; `face_flip`; `vert_dissolve` (grid center → `True`); `edge_split` (position
  at 25 %, faces with extra corner, `"edge_split"`); `face_split` (quad → 2 triangles, return, adjacent
  vertices → `"face_split"`, `coords` → NI); `intersect_face_point` (inside, outside, border, point off the
  plane).
- `tests/bmesh/test_convert_roundtrip.py`: no fixture — bit-for-bit round trip (§3.3.3,
  `bmesh_to_geometry`) of the 9 primitives of `quartz.geometry.primitives`, of `from_pydata` with a quad and a
  loose edge, and of a geometry with one attribute of each of the 12 types of `DATA_TYPES` in each
  of the 4 domains, with visible names and with a leading `.`, plus `.pn.UVMap` (consumed) and
  `.pn.Nothing` without a UV of the same name (hidden); table of consumed attributes (defaults when absent, writing only
  if present or non-default, `BYTE_COLOR` exact); invalid geometry → `ValueError` with
  `"invalid geometry"`; joining when called twice (summed counts, shifted indices); editing
  (moving vertices, `faces.new`, removing) is reflected in the geometry; local fake `MeshLike` (class with
  `q_geometry`/`q_set_geometry`) for `from_mesh`/`to_mesh`, `"expected a Mesh"`, `"is in editmode"`,
  active UV; with `qz` (gate) — round trip of the factory Cube (`data.meshes["Cube"]` → `BMesh` →
  `data.meshes.new("X")`, same geometry) and `from_object` of the Cube.
- `tests/bmesh/test_editmode.py` (fixture `qz`; gate): `quartz.ops.call("object.mode_set",
  mode="EDIT")` with the Cube active;
  `from_edit_mesh` returns the same `BMesh` twice, `is_wrapped`, `q_mesh`; mesh outside edit mode →
  `ValueError` with `"must be in editmode"` (also in `update_edit_mesh`); moving all vertices +
  `update_edit_mesh` → `mesh.vertices[0].co` has already changed (also after
  `quartz.types.mesh.set_editmode_hooks()` has removed the hook); `Object.update_from_editmode()` writes;
  `mode_set(mode="OBJECT")` writes and clears `q_edit_data`; the old BMesh stays alive and detached;
  re-entering creates a new BMesh; entering/leaving without
  `from_edit_mesh` does not change the geometry; `free()` of the edit BMesh is a no-op; `to_mesh` on the mesh in
  edit mode → `"is in editmode"`; `select_mode` from `tool_settings.mesh_select_mode`;
  `install_adapters()` idempotent and `BVHTree.FromBMesh` of `create_cube(size=2.0)` hits the ray from
  (0, 0, 5) toward −Z at z = 1 with normal (0, 0, 1) and `index` = position of the top face in `bm.faces`,
  without changing the `index` of the elements; tolerance to a missing `quartz.types.mesh`
  (`monkeypatch.setitem(sys.modules, "quartz.types.mesh", None)` makes the import raise
  `ModuleNotFoundError` with that `.name`: `install_adapters()` does not raise and `FromBMesh` works);
  subprocess `[sys.executable, "-I", "-c", ...]` (the code puts the root in `sys.path`) proves that
  `import quartz.bmesh, quartz.bmesh.convert, quartz.bmesh.ops` does not install an adapter
  (`quartz.math.bvhtree.BVHTree.FromBMesh(quartz.bmesh.new())` → `NotImplementedError` with
  `"adapter not installed"`).
- `tests/compat/test_bmesh_shim.py` (fixture `bpy`; gate): `import bmesh` with `dir(bmesh)` ⊇ the 7
  names of `extras.bmesh.__module__`; `bmesh.types`, `bmesh.ops`, `bmesh.utils`, `bmesh.geometry`
  are the shim modules (`sys.modules["bmesh.ops"] is bmesh.ops`) and each dump name in them is
  identical (`is`) to the one in `quartz.bmesh.<sub>`; `bmesh.new is quartz.bmesh.new` (likewise `from_edit_mesh`,
  `update_edit_mesh`); no `q_`/`_q_` name, nor `install_adapters`, exported; the import installed the adapters
  (`mathutils.bvhtree.BVHTree.FromBMesh` works); flows in the style of the Blender templates written
  by the test itself: `bmesh.new()` + `from_mesh` + move vertices + `to_mesh` + `free`; `from_edit_mesh`
  after `bpy.ops.object.mode_set(mode="EDIT")` + `faces.active = None` + `update_edit_mesh(me,
  loop_triangles=True)`; user operator that creates a mesh with `verts.new`, `ensure_lookup_table`,
  `faces.new` and `to_mesh`; `bm.loops.layers.uv.verify()` + `loop[uv].uv = loop.vert.co.xy`;
  `bmesh.ops.triangulate(bm, faces=bm.faces)` on a temporary mesh copy.

### 3.4 Add-on and extension loader (`l3-addons`)

Package `quartz.addons` (discovery, metadata, manifest, `enable`/`disable`/`check` cycle,
reports and leaks), the facade `compat/addon_utils.py` and the add-on fixtures. The normative
sequence of `enable`/`disable`/`check` is in §3.0.4; this section details it and does not contradict it.
Mark **[L]**: see §2.0.3.

General rules of the task:

1. **Imports**: `bl_info.py`, `manifest.py`, `discovery.py` and `report.py` import only stdlib
   (`ast`, `tomllib`, `importlib`, `re`, `os`, `sys`, `types`, `dataclasses`, `pathlib`) and L1
   (`quartz.errors`, `quartz.path`, `quartz.app`). `manager.py` imports L2 (`quartz.session`,
   `quartz.registry`, `quartz.types.ui`) **inside** functions/methods, and `quartz.compat` only inside
   `AddonManager.enable` and `AddonManager.enable_with_report` (§0.6: compat only serves Blender
   add-ons), always as `compat = importlib.import_module("quartz.compat")` (the object that is in
   `sys.modules`; never `quartz.compat` through the package attribute, so that a fake compat injected into
   `sys.modules` by the tests is the one used). This way `import quartz.addons` works with L1 only.
2. **No import effect** (§3.0.2): importing any module of `quartz.addons` (including creating
   `MANAGER`) MUST NOT touch `sys.path`, `sys.modules`, session, registry, hooks or handlers.
   `discover`, `locate`, `read_bl_info`, `parse_manifest`, `modules`/`modules_refresh` and `check`
   NEVER alter `sys.path`/`sys.modules`; they only change inside `ensure_extension_packages`,
   `sync_sys_path`, `enable` (and whoever calls it: `reset_all`, `extensions_refresh`,
   `enable_with_report`) and `q_reset`. `disable` does not remove the module from `sys.modules` **[O]**.
3. **Prints**: only the default `handle_error` writes (traceback to `sys.stderr`, allowed by §0.1(6)).
   Warnings go to lists (`problems`, `Manifest.warnings`, `MANAGER.q_warnings`,
   `AddonReport.warnings`).
4. Dispatches: only this task dispatches `addon_enable_post`/`addon_disable_post` (§2.1.2), always through
   `quartz.app.handlers.dispatch(name, module_name)`.
5. Owners: everything an add-on registers during `enable`/`disable` happens under
   `quartz.registry.owner_scope(module_name)`; reports and leaks ignore owners that start with
   `"quartz."` (built-in operators `"quartz.builtin"`, placeholders `"quartz.compat"`/
   `"quartz.placeholder"`), which by construction are never `module_name`.

#### 3.4.1 `quartz/addons/__init__.py`

```python
from quartz.addons.bl_info import BL_INFO_BASIS, MANUAL_URL, read_bl_info, module_bl_info
from quartz.addons.manifest import BLENDER_MANIFEST, QUARTZ_MANIFEST, Manifest, parse_manifest, manifest_to_bl_info
from quartz.addons.discovery import (EXT_BASE_PKG, QZ_EXT_BASE_PKG, AddonInfo, discover,
                                     ensure_extension_packages, sync_sys_path)
from quartz.addons.report import RegisteredItem, AddonReport
from quartz.addons.manager import AddonManager, MANAGER
# module functions delegated to MANAGER (same signatures as the methods, without self):
def paths() -> list[str]
def modules(*, module_cache: dict | None = None, refresh: bool = True) -> list[ModuleType]
def modules_refresh(*, module_cache: dict | None = None) -> None
def enable(module_name: str, *, default_set: bool = False, persistent: bool = False, refresh_handled: bool = False,
           handle_error: Callable[[BaseException], None] | None = None) -> ModuleType | None
def disable(module_name: str, *, default_set: bool = False, refresh_handled: bool = False,
            handle_error: Callable[[BaseException], None] | None = None) -> None
def check(module_name: str) -> tuple[bool, bool]
def check_extension(module_name: str) -> bool
def disable_all() -> None
def reset_all(*, reload_scripts: bool = False) -> None
def extensions_refresh(ensure_wheels: bool = True, addon_modules_pending: Sequence[str] | None = None,
                       handle_error: Callable | None = None) -> None
# module_bl_info is the bl_info.py object itself (does not go through MANAGER)
__all__: list[str]    # all the names above
```

- Each delegated function is an ordinary Python function defined in this module (stable identity:
  `compat/addon_utils.py` re-exports them, §3.4.7) and calls the method of the same name on `MANAGER` at the time
  of the call (never a bound method captured at import).
- `quartz.addons.module_bl_info is quartz.addons.bl_info.module_bl_info`.

#### 3.4.2 `quartz/addons/bl_info.py`

```python
BL_INFO_BASIS: Mapping[str, object]   # MappingProxyType, in this order [O] (probes.addon_lifecycle.bl_info_basis):
    # name "", author "", version (), blender (), location "", description "", doc_url "", support "COMMUNITY",
    # category "", warning "", show_expanded False
MANUAL_URL: str = "https://docs.blender.org/manual/en/5.2"     # value of {BLENDER_MANUAL_URL} [I]
def read_bl_info(path: str | Path, *, fast: bool = True, problems: list[str] | None = None) -> dict | None
def module_bl_info(mod: ModuleType, *, info_basis: Mapping[str, object] | None = None) -> dict
```

`read_bl_info(path)` — reads **without importing** **[L]**:

1. `path` a directory → uses `path/__init__.py`. Missing file → `None` and problem
   `f'"{path}" not found'`.
2. Reads the bytes and decodes UTF-8 (with `utf-8-sig`, tolerating a BOM). Decoding failure →
   `None` and problem with the fragment `"is not UTF-8"`.
3. `fast=True`: the snippet starts at the first line that **starts** (column 0) with `bl_info` and goes to
   the first line whose `strip()` is empty (exclusive) or the end of the file **[L]**. No such line →
   `None` and problem `'no "bl_info" found'`. The snippet is parsed with `ast.parse` and may contain
   other statements after `bl_info` (code pasted without a blank line, as in the add-on of the probe
   `probes.addon_lifecycle`): the **first** top-level statement of the snippet that is an
   `ast.Assign` with a single `ast.Name` target `bl_info` counts **[L]** (or `ast.AnnAssign` `bl_info: dict =
   ...` **[I]**); the other statements are ignored (never executed). The value goes through
   `ast.literal_eval` **[L]**. No such assignment in the snippet → `None` and `'no "bl_info"
   found'`. `SyntaxError`/`ValueError` (non-pure literal, or blank line inside the dictionary,
   which cuts the snippet) → `None` and problem with `'"bl_info" could not be parsed'`.
4. `fast=False`: `ast.parse` of the whole file and the first module-level assignment to
   `bl_info` (same node rule as step 3), with `ast.literal_eval` on the value; same failures and
   messages.
5. Value that is not a `dict` → `None` and problem `'"bl_info" is not a dict'`. Success returns a new `dict`,
   raw (without completing the basis). No code from the file is executed.
6. `problems`, when given, receives the messages (appended); the function never raises because of the content of the
   file (only `TypeError` for an argument).

`module_bl_info(mod, *, info_basis=None)` — normalizes **in place** and returns the module's dictionary:

1. `info = getattr(mod, "bl_info", None)`; missing or not a `dict` → `info = {}` and `mod.bl_info = info`.
2. `"_init" in info` → returns `info` as is (same object; already normalized) **[L]**.
3. Completes the missing keys with the basis (`info_basis` or `BL_INFO_BASIS`), in the order of the basis, after
   the keys already present (which keep their original order) **[O]** (dump order:
   `name, author, version, blender, category, location, description, doc_url, support, warning,
   show_expanded, _init` for a `bl_info` with the first five).
4. Empty `name` → `mod.__name__` **[L]**.
5. `author` `str`: removes each occurrence of "optional whitespace followed by `<...>`" (the shortest possible
   `<...>`, regex `\s*<.*?>`), without any other `strip` **[L]**; `"D1on1n <x@y.z>"` →
   `"D1on1n"` **[O]**. An `author` that is not a `str` stays as it came.
6. `doc_url` `str` containing `"{BLENDER_MANUAL_URL}"` → replaces it with `MANUAL_URL` **[L]**.
7. `info["_init"] = None` (normalized marker) **[O]** and returns `info`. Values of an
   unexpected type (e.g. `version` a list) stay as they came.

#### 3.4.3 `quartz/addons/manifest.py`

```python
BLENDER_MANIFEST: str = "blender_manifest.toml"     # [O] probes.addon_lifecycle.ext_manifest_filename
QUARTZ_MANIFEST: str = "quartz_manifest.toml"
MANIFEST_TYPES: tuple[str, ...] = ("add-on", "theme")                                         # [L]
PERMISSION_KEYS: tuple[str, ...] = ("files", "network", "clipboard", "camera", "microphone")  # [L]
REQUIRED_BLENDER: tuple[str, ...] = ("schema_version", "id", "name", "tagline", "version", "type", "maintainer",
                                     "license", "blender_version_min")                        # [L]
REQUIRED_QUARTZ: tuple[str, ...] = ("schema_version", "id", "name", "tagline", "version", "type", "maintainer",
                                    "license", "quartz_version_min")                         # [I]
@dataclass
class Manifest:
    schema_version: str; id: str; name: str; tagline: str; version: str; type: str; maintainer: str; license: list[str]
    blender_version_min: str | None; blender_version_max: str | None = None; quartz_version_min: str | None = None
    website: str | None = None; copyright: list[str] = field(default_factory=list); permissions: dict[str, str] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list); platforms: list[str] = field(default_factory=list); wheels: list[str] = field(default_factory=list)
    build: dict[str, object] = field(default_factory=dict); path: str = ""; native: bool = False
    warnings: list[str] = field(default_factory=list)          # non-fatal warnings (wheels, unknown keys, id ≠ folder)
def parse_manifest(path: str | Path, *, strict: bool = True) -> Manifest
def manifest_to_bl_info(manifest: Manifest) -> dict
def version_tuple(text: str) -> tuple[int, ...]     # "1.2.3-rc1" -> (1, 2, 3); component with leading digits only [L]; no digits -> 0
```

`parse_manifest(path, *, strict=True)`:

1. `path` a directory → `path/blender_manifest.toml` if it exists, otherwise `path/quartz_manifest.toml`;
   `path` a file → the file itself; nonexistent (or a directory with neither of the two) →
   `ManifestError(["manifest not found"], str(path))`. `native = (file name ==
   QUARTZ_MANIFEST)`; `Manifest.path = str(file)`; the `path` of every following `ManifestError` is
   `str(file)`.
2. `tomllib.loads` of the UTF-8 text; decoding or TOML error →
   `ManifestError([f"invalid TOML: {exc}"], str(file))` (single problem).
3. Collects **all** problems in a list and, if it is not empty, raises **one** `ManifestError(problems,
   str(file))` at the end (§1.3: `str(exc)` joins with `"; "`) **[L]**. Deterministic order of the
   problems: that of the rows of the table below; within a row, the order of the `REQUIRED_*` tuple (or
   of the row's field list). A missing field generates only the missing-field problem (without the type one).
   Rules and message fragments:

| Rule | Problem (verified fragment) |
|---|---|
| required field missing (`REQUIRED_BLENDER` or, if `native`, `REQUIRED_QUARTZ`) | `f'missing required field "{k}"'` |
| `schema_version, id, name, tagline, version, type, maintainer, website`, versions: `str` | `f'field "{k}" must be a string'` |
| `license, copyright, tags, platforms, wheels`: list of `str` (`license` non-empty) | `f'field "{k}" must be a list of strings'` |
| `type` outside `MANIFEST_TYPES` | `'"type" must be one of ("add-on", "theme")'` |
| `id` not a Python identifier / containing `"__"` / starting or ending with `"_"` **[L]** | `f'"id" "{id}" is not a valid identifier'`, `'"id" must not contain "__"'`, `'"id" must not start or end with "_"'` |
| `version` without the form `N.N.N` (suffix `-…`/`+…` accepted) **[I]** | `f'"version" "{v}" is not a valid version'` |
| `blender_version_min`/`blender_version_max`/`quartz_version_min`: strict → exactly 3 numbers separated by `.`; non-strict → 1 to 3 **[L]**; `blender_version_max == ""` → treated as `None` **[L]** | `f'"{k}" "{v}" must be 3 numbers'` (strict) / `f'"{k}" "{v}" is not a valid version'` |
| `copyright`: each item matches `^\d{4}(-\d{4})? \S.*$` **[L]** | `f'"copyright" entry "{c}" must look like "YEAR Name" or "YEAR-YEAR Name"'` |
| `permissions`: non-empty `str -> str` table, keys in `PERMISSION_KEYS`; non-strict also accepts a list of keys (becomes `{key: ""}`) **[L]** | `'"permissions" must be a table'`, `f'unknown permission "{k}"'` |
| `[build]` with `paths` **and** `paths_exclude_pattern` **[L]** | `'"[build]" cannot define both "paths" and "paths_exclude_pattern"'` |
| `[build]` not a table | `'"build" must be a table'` |

4. No problems: fills in the `Manifest` (missing optional fields with the dataclass defaults) and
   appends to `warnings`: `f'wheels are not supported in Quartz: {n} wheel(s) ignored'` if
   `wheels` is non-empty **[I]**; `f'unknown field "{k}" ignored'` for an unknown top-level key
   (not a problem even in strict mode **[I]**). `blender_version_min` in a native manifest is optional and
   kept.

`manifest_to_bl_info(manifest)` → new `dict` that starts as a copy of `BL_INFO_BASIS` (same key
order) and overwrites **[L]**: `name ← name`, `version ← version_tuple(version)`, `blender ←
version_tuple(blender_version_min)` (`()` if `None`), `description ← tagline`, `author ←
maintainer`, `category = "Development"` (fixed). The final key order is therefore that of
`BL_INFO_BASIS`. It does not add `"_init"` (`module_bl_info` completes it later, without reordering).

#### 3.4.4 `quartz/addons/discovery.py`

```python
EXT_BASE_PKG: str = "bl_ext"                 # [O] probes.addon_lifecycle.ext_base_pkg
QZ_EXT_BASE_PKG: str = "qz_ext"
ADDON_KINDS: tuple[str, ...] = ("LEGACY_FILE", "LEGACY_PACKAGE", "EXTENSION", "NATIVE_EXTENSION")
@dataclass
class AddonInfo:
    module_name: str; path: Path; kind: str   # "LEGACY_FILE" | "LEGACY_PACKAGE" | "EXTENSION" | "NATIVE_EXTENSION"
    bl_info: dict | None; manifest: Manifest | None; repo: str | None; mtime: float
    problems: list[str] = field(default_factory=list)   # missing/invalid metadata (messages from read_bl_info/ManifestError)
def discover(*, include_extensions: bool = True, duplicates: list[tuple[str, str, str]] | None = None) -> list[AddonInfo]
def ensure_extension_packages() -> None
def sync_sys_path() -> None
def locate(module_name: str) -> AddonInfo | None     # discover() by name; otherwise (name without ".") PathFinder.find_spec without importing
```

`discover()`:

1. **Legacy add-ons** **[L]**: for each `d` in `quartz.app.paths.addon_dirs()` that exists (list order),
   `quartz.path.module_names(str(d))`; the name `"modules"` is ignored. `path` = the `.py` (`LEGACY_FILE`) or
   `folder/__init__.py` (`LEGACY_PACKAGE`); `bl_info = read_bl_info(path, problems=info.problems)`
   (may be `None`: the target still appears, with the problem); `manifest=None`, `repo=None`,
   `mtime = os.path.getmtime(path)`. Same module in two directories: the first one wins;
   `duplicates`, if given, receives `(name, kept_path, ignored_path)` with `name =
   bl_info["name"]` of the kept one (or `module_name` if there is none) and `str` paths **[L]** (this is the format
   of `addon_utils.error_duplicates`).
2. **Extensions** (if `include_extensions`): for each `(repo, dir)` of
   `quartz.app.paths.extension_repos()` with an existing `dir`, each non-hidden subfolder other than
   `__pycache__`, in name order: with `blender_manifest.toml` → `EXTENSION`, module
   `f"bl_ext.{repo}.{folder}"`; otherwise with `quartz_manifest.toml` → `NATIVE_EXTENSION`, module
   `f"qz_ext.{repo}.{folder}"`; with neither → ignored. Both manifests in the same folder →
   the Blender one wins and the warning `"both manifests found; quartz_manifest.toml ignored"` goes into
   `problems` **[I]**. The last component of the module (the `<id>` of `bl_ext.<repo>.<id>`) is the **folder
   name**, which is what the import resolves **[L]** (in an installed repository the folder and `id`
   coincide; all the fixtures in §3.4.8 have `id` == folder). `id` ≠ folder → warning
   `f'manifest id "{id}" differs from directory "{folder}"'` in `manifest.warnings` **[I]** (added
   by `discover` and by step 3 of `enable`). `manifest = parse_manifest(kind_file,
   strict=False)` with `kind_file` = `folder/blender_manifest.toml` (`EXTENSION`) or
   `folder/quartz_manifest.toml` (`NATIVE_EXTENSION`); `ManifestError` → `manifest=None` and
   `problems.extend(exc.problems)`; success → `bl_info = manifest_to_bl_info(manifest)`. `repo` =
   repository name; `path = folder/__init__.py` (missing → problem `'missing "__init__.py"'`,
   `mtime = 0.0`; otherwise `mtime = os.path.getmtime(path)`).
3. Result order: `(name.casefold(), module_name)`, with `name = (bl_info or {}).get("name")`
   or `manifest.name` or `module_name` **[L]**.
4. Never imports add-on code or changes `sys.path`/`sys.modules`.

`ensure_extension_packages()` **[O name]**: for `base` in (`EXT_BASE_PKG`, `QZ_EXT_BASE_PKG`) and each
`(repo, dir)` of `extension_repos()`: ensures in `sys.modules` a `types.ModuleType(base)` with
`__path__ = []`, `__package__ = base`, `__spec__ = importlib.machinery.ModuleSpec(base, None,
is_package=True)` and the attribute `__quartz_synthetic__ = True`; and an identical `f"{base}.{repo}"` with
`__path__ = [str(dir)]` (list updated **in place** if it already exists; the same list object is
`__spec__.submodule_search_locations`), bound as attribute `repo` of the parent. Idempotent. A
**non**-synthetic module with the same name already present → left as is (nothing is overwritten) **[I]**.

`sync_sys_path()`: appends to the end of `sys.path` each `str(d)` of `addon_dirs()` that exists and is absent
**[I]**, and remembers what it appended (undone by `MANAGER.q_reset()`).

`locate(module_name)`: first `AddonInfo` from `discover()` with that `module_name`; otherwise, for a name
without `"."`, `importlib.machinery.PathFinder.find_spec(module_name, sys.path)` (imports nothing):
`.py` origin → `AddonInfo(kind="LEGACY_FILE")`, package with `__init__.py` (`spec.origin`) →
`"LEGACY_PACKAGE"`, with `path = Path(spec.origin)`, `bl_info` and `problems` read as in step 1,
`manifest=None`, `repo=None`, `mtime` of the file; namespace package, binary extension or nothing
found → `None`.

#### 3.4.5 `quartz/addons/manager.py`

```python
class AddonManager:
    addons_fake_modules: dict[str, ModuleType]       # stable identity for the whole life of the object (mutated in place)
    error_duplicates: list[tuple[str, str, str]]     # same; filled by modules_refresh
    error_encoding: bool                             # True if some bl_info is not UTF-8 (last modules_refresh)
    q_warnings: dict[str, list[str]]                 # module -> warnings of the last enable/extensions_refresh
    def __init__(self) -> None                       # empty state only; no effect
    def paths(self) -> list[str]
    def modules(self, *, module_cache: dict | None = None, refresh: bool = True) -> list[ModuleType]
    def modules_refresh(self, *, module_cache: dict | None = None) -> None
    def enable(self, module_name: str, *, default_set: bool = False, persistent: bool = False, refresh_handled: bool = False,
               handle_error: Callable[[BaseException], None] | None = None) -> ModuleType | None
    def disable(self, module_name: str, *, default_set: bool = False, refresh_handled: bool = False,
                handle_error: Callable[[BaseException], None] | None = None) -> None
    def check(self, module_name: str) -> tuple[bool, bool]                     # (loaded_default, loaded_state) [O]
    def check_extension(self, module_name: str) -> bool                        # prefix "bl_ext." [L] or "qz_ext." [I]
    def disable_all(self) -> None
    def reset_all(self, *, reload_scripts: bool = False) -> None
    def extensions_refresh(self, ensure_wheels: bool = True, addon_modules_pending: Sequence[str] | None = None,
                           handle_error: Callable | None = None) -> None
    def enable_with_report(self, module_name: str, *, smoke: Callable[[str], Mapping[str, int]] | None = None,
                           keep_enabled: bool = False) -> AddonReport
    def leaks(self, module_name: str) -> list[str]
    def pin_annotations(self, module: ModuleType, *, warnings: list[str] | None = None) -> int
    def q_reset(self) -> None
MANAGER: AddonManager        # created at import (no effect); stable identity
```

Notation: `prefs = quartz.session.current().preferences`; "submodules of `m`" = names in
`sys.modules` equal to `m` or starting with `m + "."`; `mtime(mod)` =
`os.path.getmtime(mod.__file__)` (no `__file__` or OS error → `None`).

**`paths()`** **[L]**: `str(d)` for each `d` of `addon_dirs()` that exists, in order, without repetition.
Does not include extension repositories.

**`modules_refresh(*, module_cache=None)`** **[L]**: `cache = module_cache` if given, otherwise
`self.addons_fake_modules`. `infos = discover(include_extensions=True, duplicates=dups)`; for each
`info` with `bl_info is not None`: reuses `cache[name]` if `__file__ == str(info.path)` and
`__time__ == info.mtime`; otherwise creates `types.ModuleType(info.module_name)` with `bl_info` (copy of
`info.bl_info`), `__file__ = str(info.path)`, `__time__ = info.mtime`. Then `cache.clear();
cache.update(new)` (in place); `self.error_duplicates[:] = dups`; `self.error_encoding = any(
"is not UTF-8" in p for info in infos for p in info.problems)`. Imports nothing.

**`modules(*, module_cache=None, refresh=True)`**: if `refresh` or the effective cache is empty →
`modules_refresh(module_cache=module_cache)`; returns a new list with the cache values
sorted by `(bl_info.get("category", ""), bl_info.get("name", ""))` **[L]**, with a
stable tie-break by `__name__` **[I]** (the `bl_info` of the fake modules is raw, hence `.get`).

**`enable(module_name, ...)`** — the sequence from §3.0.4, with these details:

0. `self.q_warnings[module_name] = []` (new list; the following steps append to it).
1. **Compat**: `module_name` does not start with `"qz_ext."` → `compat =
   importlib.import_module("quartz.compat")`; if `not compat.is_active()` →
   `compat.activate(strict=False)`; never deactivates afterwards. `ModuleNotFoundError` whose `.name ==
   "quartz.compat"` (missing sibling, or `sys.modules["quartz.compat"] is None`) → continues without compat and
   records `"quartz.compat unavailable"` in `q_warnings[module_name]` **[I]**; `CompatError` or another
   exception from the activation → failure path (step 7), before any import.
2. `sync_sys_path()`; `ensure_extension_packages()`.
3. **Manifest** (only names that start with `"bl_ext."`/`"qz_ext."`): the name MUST have exactly three
   components `<base>.<repo>.<folder>`, with `repo` in `quartz.app.paths.extension_repos()`; otherwise
   → `ModuleNotFoundError(f"No module named '{module_name}'", name=module_name)`, which goes on to
   step 7. File: `repo_dir / folder / BLENDER_MANIFEST` for `bl_ext.`, `... /
   QUARTZ_MANIFEST` for `qz_ext.` (never the other one); `parse_manifest(file, strict=False)`
   (nonexistent → `ManifestError` `"manifest not found"`); `ManifestError` → failure; `type ==
   "theme"` → failure with `ManifestError(['"type" "theme" cannot be enabled as an add-on'], path)`
   **[I]**; native with `version_tuple(quartz_version_min) > quartz.app.version` → failure with
   `ManifestError([f"requires Quartz {v} or newer"], path)` (`v` = the manifest text) **[I]**;
   Blender extension with `version_tuple(blender_version_min) > (5, 2, 2)` or
   `version_tuple(blender_version_max) <= (5, 2, 2)` (version emulated by compat **[O]**) → only the
   warning `f"manifest targets Blender {min}..{max}; compat emulates 5.2.2"` in `q_warnings` **[I]**;
   `manifest.warnings` (with the `id` ≠ folder warning, §3.4.4) are copied to `q_warnings`.
4. **Re-entry** **[L]**: `mod = sys.modules.get(module_name)`; if `mod` and
   `getattr(mod, "__addon_enabled__", False)`: `mod.__addon_enabled__ = False`, removes `module_name`
   from the internal enable order, `mod.unregister()` under `owner_scope(module_name)` (exception →
   `handle_error`, continues); marks for reload if `mtime(mod)` is not `None` and differs from
   `getattr(mod, "__time__", None)`. Nothing is dispatched here.
5. `default_set=True` and `module_name not in prefs.addons` → `prefs.addons.new().module =
   module_name` **before** the import **[L]**.
6. Inside `quartz.session.restrict_blend()` (default: `settings.restrict_register`) and
   `quartz.registry.owner_scope(module_name)`, in this order: (a) `mod = importlib.reload(mod)` if
   marked for reload, otherwise `importlib.import_module(module_name)` (a module already in `sys.modules` and
   disabled is reused, without re-executing **[L]**); right after the import, **always**
   `mod.__time__ = mtime(mod)` (or `0.0` if `None`) **[L]** — this is what re-entry compares; (b)
   `pin_annotations(mod, warnings=q_warnings[module_name])`; (c) extension (both kinds):
   `mod.__dict__.pop("bl_info", None)`; `mod.bl_info = manifest_to_bl_info(manifest)` **[L]**; (d)
   `mod.register()` (missing attribute → the `AttributeError` is the failure).
7. **Failure** (any exception from steps 1, 3 and 6): if it is a `ModuleNotFoundError` with `exc.name`
   not `None` and (`exc.name == module_name` or `module_name.startswith(exc.name + ".")`), replaces it with
   `ModuleNotFoundError(f'Add-on not loaded: "{module_name}", cause: {exc}')` (`name=module_name`,
   chained with `from exc`) **[O]**; a dependency missing inside the add-on (another `exc.name`) passes
   through without replacement. Calls `handle_error(exc)` (default: `traceback.print_exception(exc,
   file=sys.stderr)`); removes the module and its submodules from `sys.modules`; if `default_set`, removes
   `module_name` from `prefs.addons` (if present) **[L]**; returns `None` **[O]**. Classes, props,
   menu extensions and handlers created before the failure remain (they show up in `leaks`) **[O]**.
   Nothing is dispatched.
8. **Success**: `mod.__addon_enabled__ = True`; `mod.__addon_persistent__ = persistent` **[O]**
   (`__time__` already written in 6(a) **[O]**); appends `module_name` to the end of the internal enable
   order; `dispatch("addon_enable_post", module_name)`; returns `mod` **[O]**.
   `refresh_handled` and `persistent` do not change the behavior (there is no UI or file switch
   that unloads add-ons) **[I]**.

**`disable(module_name, ...)`** **[O]**: `mod = sys.modules.get(module_name)`; if `mod` and
`__addon_enabled__`: `mod.__addon_enabled__ = False`, `mod.__addon_persistent__ = False`,
`mod.unregister()` under `owner_scope(module_name)` (without RestrictBlend **[L]**; exception →
`handle_error`, does not propagate), removes from the enable order and `dispatch("addon_disable_post",
module_name)` — dispatched whenever the add-on was enabled, even if `unregister()` raised
**[I]**. Not enabled → none of this. Then, `default_set=True` → removes from `prefs.addons` if
present. The module **stays** in `sys.modules` **[O]**.

**`check(module_name)`** → `(module_name in prefs.addons, bool(mod) and getattr(mod,
"__addon_enabled__", False) is True)` **[O]**: `(False, False)` before; `(True, True)` after
`enable(default_set=True)`; `(False, False)` after `disable(default_set=True)`.

**`disable_all()`**: takes a copy of the internal enable order and calls `disable(m)`
(`default_set=False`) for each name, in **reverse** order **[I]**, skipping those that are no longer
enabled when their turn comes (the `unregister` of one may disable another) **[L]**.

**`reset_all(*, reload_scripts=False)`** **[I]**: syncs with `prefs.addons`, in order: (1) with
`reload_scripts=True`, each enabled add-on (reverse enable order) is disabled
(`default_set=False`) and removed from `sys.modules` along with its submodules; (2) enabled add-ons absent from
`prefs.addons` are disabled (`default_set=False`); (3) each entry of `prefs.addons` (collection order) that is not
enabled is enabled with `enable(m)` (`default_set=False`; with `reload_scripts` this
reimports).

**`extensions_refresh(ensure_wheels=True, addon_modules_pending=None, handle_error=None)`** **[I]**:
`ensure_extension_packages()`; then `enable(m, default_set=True, handle_error=handle_error)`
for each `m` of `addon_modules_pending`, in order; finally, if `ensure_wheels`, for each
extension from `discover()` with non-empty `manifest.wheels`, appends `"wheels are not supported in
Quartz; nothing was installed"` to `q_warnings.setdefault(module, [])` (after the `enable` calls, which
reset the module's list in step 0, so that the warning survives). Nothing is downloaded or installed;
`sys.path` does not change because of wheels.

**`pin_annotations(module, *, warnings=None)`**: for the module and each already loaded submodule, for
each module-level class whose `__module__` is that module (and, recursively, classes nested
in the `__dict__` of those classes with the same `__module__`), in `__dict__` order: reads
`cls.__annotations__` once. In Python 3.14 the first read calls `__annotate__` and stores the
result in the class cache (`__annotations_cache__`, without creating `"__annotations__"` in the
`__dict__`); `annotationlib.get_annotations(cls, format=Format.VALUE)`, used by the registry
(§1.6.6), returns that cache. This way the defaults are pinned with the globals as of the end of the import, as
in the eager evaluation of 3.13. In 3.13, or with `from __future__ import annotations`, the read is
harmless. It NEVER assigns, deletes or replaces `__annotations__`, `__annotate__` or the cache. Exception in
the evaluation (e.g. `NameError` from a forward reference) → appends `f"{cls.__qualname__}: annotations
not pinned ({type(exc).__name__}: {exc})"` to `warnings` (if given) and continues (the registry tries later
with `FORWARDREF`, §1.6.6). Returns the number of classes whose read succeeded and was non-empty.

**`leaks(module_name)`** — what still exists of the owner `module_name`, in this order and format:

1. `f"class {base}:{rna}"` for each `cls` of `quartz.registry.classes_owned_by(module_name)` with
   `registry.is_registered(cls)` (`base = registry.registrable_base_of(cls).__name__`, `rna =
   registry.rna_name_of(cls)`), in registration order;
2. `f"property {T}:{ident}"` for each `(T, ident)` of `registry.type_props_owned_by(module_name)`,
   in the order returned (`T` = `T.bl_rna.identifier` if present, otherwise `T.__name__`);
3. `f"menu {M}:{q}"` for each `(cls, fn)` of `quartz.types.ui.draw_funcs_owned_by(module_name)`,
   in the order returned, with `M = registry.rna_name_of(cls)`;
4. `f"handler {name}:{q}"` for each function of each list of `quartz.app.handlers.all_lists()`
   (list order, then order within the list) whose `getattr(fn, "__module__", None)` is
   `module_name` or starts with `module_name + "."`.

In 3 and 4, `q = getattr(fn, "__qualname__", None) or repr(fn)`. No repeated item; new list on
each call. Does not use the session.

**`enable_with_report(module_name, *, smoke=None, keep_enabled=False)`** → `AddonReport`; never
raises because of the add-on (exceptions from `smoke` and from the add-on are caught). `t0 =
time.perf_counter()`; `compat_mod = sys.modules.get("quartz.compat")` (only counts if it is a module,
not `None`); initial count = `collections.Counter(compat_mod.missing_symbols())` (copy) if
present, otherwise `Counter()`. Initial values: `reached = "NONE"`, empty lists/dictionaries,
`error_type = error = traceback = None`.

1. `info = locate(module_name)`; `kind = info.kind` or `"UNKNOWN"` (outside `ADDON_KINDS`).
   `None` → `error_type="ModuleNotFoundError"`, `error = f'Add-on not loaded: "{module_name}",
   cause: not found in add-on paths or extension repositories'`; goes to step 7.
2. **METADATA**: legacy with `info.bl_info` not `None`, or extension with `info.manifest` not `None` →
   `reached = "METADATA"`. Otherwise `error_type = "ManifestError"`, `error = "; ".join(info.problems)`
   (e.g. `'no "bl_info" found'`), `info.problems` go into `warnings`; goes to step 7 (no import).
3. `mod = enable(module_name, default_set=True, handle_error=<collector>)`. During `enable` the
   manager stores the phase in an internal attribute (`_q_*`, free name): `"IMPORT"` immediately
   before 6(a) and `"REGISTER"` immediately before 6(d). Failure with the phase not yet set or
   `"IMPORT"` → `reached` stays `"METADATA"`; failure with phase `"REGISTER"` → `"IMPORT"`; success →
   `"REGISTER"`. The first collected exception fills in `error_type = type(exc).__name__`, `error =
   str(exc)`, `traceback = "".join(traceback.format_exception(exc))`.
4. Right after step 3 (success or failure): `registered` = `RegisteredItem(registrable_base_of(cls)
   .__name__, rna_name_of(cls), getattr(cls, "bl_idname", "") or "")` for the classes of item 1 of
   `leaks`, in the same order; `type_props_added` = `f"{T}.{ident}"` from item 2; `menus_extended` =
   `sorted` of the distinct `M` from item 3; `handlers_added` = `f"{name}:{q}"` from item 4. Failure
   (`mod is None`) → `leaks = self.leaks(module_name)`; goes to step 7.
5. **UI_SMOKE**: `smoke` given → `ui_smoke = dict(smoke(module_name))`; reaches `"UI_SMOKE"` if
   `ui_smoke.get("failed", 0) == 0`, otherwise warning `f"UI smoke failed: {n} item(s)"` (no `error`);
   exception in `smoke` → fills in `error_type`/`error`/`traceback` with it, level stays `"REGISTER"`.
   `smoke=None` → `ui_smoke = {}`, warning `"UI smoke skipped"` and the level counts as reached **[I]**.
6. **Cleanup / UNREGISTER_CLEAN**: `keep_enabled=True` → does not disable, `leaks = []`, level stays
   that of step 5. Otherwise (`enable` succeeded, whatever the smoke result was):
   `disable(module_name, default_set=True, handle_error=<collector>)`; `leaks = self.leaks(
   module_name)`; reaches `"UNREGISTER_CLEAN"` only if step 5 reached `"UI_SMOKE"`, `disable` did not
   collect an exception and `leaks == []`. An `unregister` exception collected here only fills in `error*` if
   they are still empty.
7. `missing_symbols` = `{symbol: n_final - n_initial}` only for positive increments, with
   `n_final` from `missing_symbols()` of the `quartz.compat` in `sys.modules` at the end (which may have been
   imported during `enable`); without compat → `{}`. `warnings`, in this order: problems from step 2,
   copy of `q_warnings.get(module_name, [])`, warnings from steps 5–6. `seconds =
   time.perf_counter() - t0`. Returns the `AddonReport`.

**`q_reset()`**: empties in place `addons_fake_modules`, `error_duplicates`, `q_warnings` and the enable
order; `error_encoding = False`; resets the internal phase; removes from `sys.modules` the synthetic
packages (those with `__quartz_synthetic__`) and everything under `bl_ext.`/`qz_ext.`; removes from `sys.path` what
`sync_sys_path` appended (and forgets the list). Does not disable add-ons, does not touch the registry or the
preferences (that is the job of the `qz`/`bpy` fixtures of §1.1.2, via `quartz.testing.isolated`, §2.6.8).
Idempotent.

Errors (verified by test). `enable`/`disable`/`extensions_refresh` NEVER raise because of the
add-on: every exception goes to `handle_error`. Those delivered are: `ManifestError` (`quartz.errors`,
subclass of `ValueError`) with the fragments from §3.4.3, `"manifest not found"`, `"invalid TOML"`,
`'"type" "theme" cannot be enabled as an add-on'` and `"requires Quartz"`; `ModuleNotFoundError`
(builtin) with `'Add-on not loaded: "'` and `'", cause: '` **[O]**; `CompatError` from the compat
activation; and the original exception from the import/`register()`/`unregister()` (e.g. `RestrictedAccessError`,
`RuntimeError`). `parse_manifest` raises `ManifestError`; `AddonReport(...)` with `reached` outside
`REPORT_LEVELS` raises `ValueError` (§3.4.6).

#### 3.4.6 `quartz/addons/report.py`

```python
@dataclass
class RegisteredItem:
    base: str          # name of the registrable base ("Operator", "Panel", "Menu", "Header", "UIList", "PropertyGroup", "AddonPreferences", ...)
    rna_name: str      # registry.rna_name_of(cls) ("QZ_FX_OT_single_op")
    bl_idname: str     # "" if the class has none
@dataclass
class AddonReport:
    module: str; kind: str; reached: str      # reached ∈ ("NONE", "METADATA", "IMPORT", "REGISTER", "UI_SMOKE", "UNREGISTER_CLEAN")
    registered: list[RegisteredItem]; type_props_added: list[str]; handlers_added: list[str]; menus_extended: list[str]
    ui_smoke: dict[str, int]; leaks: list[str]; missing_symbols: dict[str, int]; warnings: list[str]
    error_type: str | None; error: str | None; traceback: str | None; seconds: float
    def to_dict(self) -> dict
REPORT_LEVELS: tuple[str, ...] = ("NONE", "METADATA", "IMPORT", "REGISTER", "UI_SMOKE", "UNREGISTER_CLEAN")
```

- `reached` uses the names from §3.0.5 (without `STATIC`, which belongs to the `l3-cli-sweep` scan); a value outside
  `REPORT_LEVELS` → `ValueError` in `__post_init__`.
- `to_dict()`: all field keys, in dataclass order, with `registered` as a list of
  `{"base", "rna_name", "bl_idname"}` and lists/dicts copied, plus, last,
  `"registered_counts"`: `{base: n}` with sorted keys (without `"quartz.*"` owners, which never enter
  `registered`). The result is serializable by `json.dumps` without `default=` (only `str`, `int`,
  `float`, `bool`, `None`, `list`, `dict`).

#### 3.4.7 `compat/addon_utils.py`

```python
from quartz.addons import (paths, modules, modules_refresh, check, check_extension, enable, disable, disable_all,
                           reset_all, module_bl_info, extensions_refresh)     # same objects
addons_fake_modules = _qa.MANAGER.addons_fake_modules  # same dict (identity)
error_duplicates = _qa.MANAGER.error_duplicates        # same list (identity)
def stale_pending_stage_paths(path_base: str, paths: Sequence[str]) -> None    # no-op (there is no extension staging) [I]
def stale_pending_remove_paths(path_base: str, paths: Sequence[str]) -> None   # no-op [I]
def __getattr__(name: str) -> object
    # "error_encoding" -> _qa.MANAGER.error_encoding (read on every access); name starting with "_" -> AttributeError without noting;
    # otherwise quartz.rna.hooks.note_missing(f"addon_utils.{name}") + AttributeError(f"module 'addon_utils' has no attribute '{name}'")
def __dir__() -> list[str]               # module names ∪ {"error_encoding"}
```

- The public names (without a leading `_`) of `dir(addon_utils)` MUST be exactly the 16 in
  `probes.addon_lifecycle.addon_utils_public` **[O]**: `addons_fake_modules, check, check_extension,
  disable, disable_all, enable, error_duplicates, error_encoding, extensions_refresh,
  module_bl_info, modules, modules_refresh, paths, reset_all, stale_pending_remove_paths,
  stale_pending_stage_paths`. Every helper in the shim has a name with `_` (`import quartz.addons as
  _qa`; `import quartz.rna.hooks as _hooks`; `from collections.abc import Sequence as _Sequence`). The shim MUST NOT use `from __future__
  import annotations` (the name `annotations` would become public) nor import modules without a `_` alias.
- Thin shim (§3.0.1): it only re-exports and defines the two no-op functions; it imports stdlib and `quartz.*`,
  **never** numpy; no import side effect beyond importing `quartz.addons` (which has none).

#### 3.4.8 Fixtures `tests/fixtures/addons/**`, `tests/fixtures/extensions/**`, `tests/fixtures/native/**`

Every `.py` complies with §0.1(1) (no comments, no docstrings); the `bl_info` comes
after the `__future__` imports, is a pure literal, has no internal blank line and is
followed by one blank line. Blender add-ons import only `bpy` (compat); the native one imports only
`quartz`. No fixture writes to disk, uses the network or prints. Unless the table says otherwise,
`register()` registers the fixture's classes in the order listed (explicit loop over a `CLASSES`
tuple) and `unregister()` unregisters them in reverse order. This table is the source of the names, types
and levels consumed by the sweep (`l3-cli-sweep`, §3.5): the "Level (sweep)" column is the expected level
from §3.0.5; `MANAGER.enable_with_report(name, smoke=<smoke that does not fail>)` reaches the same level,
except where the sweep says `STATIC` (there the report stops at `reached == "NONE"`).

| File (under `tests/fixtures/`) | Kind | Required content | Level (sweep) | `registered_counts` / verifiable effect |
|---|---|---|---|---|
| `addons/qz_fx_single.py` | `LEGACY_FILE` | `bl_info` with `name "QZ FX Single"`, `author "D1on1n <d1on1n@example.invalid>"`, `version (1, 0, 0)`, `blender (4, 2, 0)`, `category "Development"`; `QZ_FX_OT_single_op` (`bl_idname "qz_fx.single_op"`, `bl_label`, `bl_options {"REGISTER", "UNDO"}`, `count: IntProperty(default=1)`, `execute` → `{"FINISHED"}`); `QZ_FX_PT_single` (`VIEW_3D`/`UI`, `bl_category "QZ FX"`, `draw`: `layout.operator("qz_fx.single_op")` and `layout.prop(context.scene, "frame_current")`) | `UNREGISTER_CLEAN` | `{"Operator": 1, "Panel": 1}` |
| `addons/qz_fx_package/__init__.py` + `ops.py` | `LEGACY_PACKAGE` | `bl_info` (`name "QZ FX Package"`); `from . import ops`; `QzFxPackagePrefs(AddonPreferences)` with `bl_idname = __package__` and `flag: BoolProperty(default=True)`; `QzFxSettings(PropertyGroup)` with `count: IntProperty(default=3)`; `register` registers the PG, prefs and each class in `ops.CLASSES`, then `bpy.types.Scene.qz_fx_settings = PointerProperty(type=QzFxSettings)`; `unregister` does `del bpy.types.Scene.qz_fx_settings` and unregisters in reverse order. `ops.py`: `QZ_FX_OT_package_op` (`"qz_fx.package_op"`) whose `execute` reads `context.preferences.addons[__package__].preferences.flag`; `CLASSES = (QZ_FX_OT_package_op,)` | `UNREGISTER_CLEAN` | `{"AddonPreferences": 1, "Operator": 1, "PropertyGroup": 1}`; `type_props_added == ["Scene.qz_fx_settings"]` |
| `addons/qz_fx_menu.py` | `LEGACY_FILE` | `bl_info`; `QZ_FX_OT_menu_op` (`"qz_fx.menu_op"`); functions `menu_import(self, context)` and `menu_object(self, context)` that call `self.layout.operator("qz_fx.menu_op")`; `register` registers the operator and does `bpy.types.TOPBAR_MT_file_import.append(menu_import)` and `bpy.types.VIEW3D_MT_object.append(menu_object)`; `unregister` removes both and unregisters | `UNREGISTER_CLEAN` | `{"Operator": 1}`; `menus_extended == ["TOPBAR_MT_file_import", "VIEW3D_MT_object"]` |
| `addons/qz_fx_future.py` | `LEGACY_FILE` | `from __future__ import annotations` (line 3); `bl_info`; `DEFAULT_COUNT = 2` defined before the class; `QZ_FX_OT_future_op` (`"qz_fx.future_op"`) with `count: IntProperty(default=DEFAULT_COUNT)` and `label: StringProperty(default="qz")` | `UNREGISTER_CLEAN` | `{"Operator": 1}`; with the add-on enabled (direct `enable` or `keep_enabled=True`), `bpy.ops.qz_fx.future_op.get_rna_type().properties["count"].default == 2` |
| `addons/qz_fx_register_fails.py` | `LEGACY_FILE` | `bl_info`; `register` registers `QZ_FX_OT_fails_op` (`"qz_fx.fails_op"`) and then `raise RuntimeError("qz_fx_register_fails: intentional failure")` | `IMPORT` | `reached == "IMPORT"`; `error_type == "RuntimeError"`; `leaks == ["class Operator:QZ_FX_OT_fails_op"]` |
| `addons/qz_fx_restricted.py` | `LEGACY_FILE` | `bl_info`; `register` reads `bpy.context.scene` before registering anything (the class `QZ_FX_OT_restricted_op` exists but is never registered) | `IMPORT` | `reached == "IMPORT"`; `error_type == "RestrictedAccessError"`; `leaks == []` |
| `addons/qz_fx_leaky.py` | `LEGACY_FILE` | `bl_info`; registers `QZ_FX_OT_leaky_op` (`"qz_fx.leaky_op"`) and `QZ_FX_PT_leaky` (`VIEW_3D`/`UI`, `draw` with a `layout.label(text="leaky")`); `unregister` unregisters only the panel | `UI_SMOKE` | `reached == "UI_SMOKE"`; `leaks == ["class Operator:QZ_FX_OT_leaky_op"]` |
| `addons/qz_fx_no_bl_info.py` | `LEGACY_FILE` | no `bl_info`; empty `register`/`unregister` | `STATIC` | `reached == "NONE"`; problem `'no "bl_info" found'` |
| `extensions/qz_fx_repo/qz_fx_ext/blender_manifest.toml` + `__init__.py` | `EXTENSION` | valid manifest (strict): `schema_version "1.0.0"`, `id "qz_fx_ext"`, `version "1.0.0"`, `name "QZ FX Extension"`, `tagline "Quartz fixture extension"`, `maintainer "D1on1n"`, `type "add-on"`, `license ["SPDX:MIT"]`, `blender_version_min "4.2.0"`. `__init__.py` defines its own `bl_info = {"name": "Ignored"}` (must be replaced), `QzFxExtPrefs(AddonPreferences)` with `bl_idname = __package__`, `QZ_FX_OT_ext_op` (`"qz_fx_ext.ext_op"`) | `UNREGISTER_CLEAN` | module `bl_ext.qz_fx_repo.qz_fx_ext`; `{"AddonPreferences": 1, "Operator": 1}`; `mod.bl_info["name"] == "QZ FX Extension"` |
| `extensions/qz_fx_repo/qz_fx_bad_manifest/blender_manifest.toml` + `__init__.py` | `EXTENSION` | other required fields valid (as in `qz_fx_ext`, `id "qz_fx_bad_manifest"`), but without `tagline`, `maintainer` and `license`; `[build]` with `paths = ["__init__.py"]` and `paths_exclude_pattern = ["*.txt"]`; valid `__init__.py` with empty `register`/`unregister` | `STATIC` | `ManifestError` with exactly 4 problems, in this order: `missing required field "tagline"`, `... "maintainer"`, `... "license"`, `cannot define both "paths" and "paths_exclude_pattern"`; `reached == "NONE"` |
| `native/qz_fx_native_repo/qz_fx_native/quartz_manifest.toml` + `__init__.py` | `NATIVE_EXTENSION` | valid native manifest: the fields of `qz_fx_ext` with `id "qz_fx_native"`, `name "QZ FX Native"`, `version "0.1.0"` and `quartz_version_min "0.1.0"` (without `blender_version_min`); `__init__.py` imports only `quartz` (uses `quartz.types.Operator`, `quartz.props.IntProperty`, `quartz.utils.register_class`/`unregister_class`); `QZ_FX_OT_native_op` (`"qz_fx_native.native_op"`, `count: IntProperty(default=1)`, `execute` → `{"FINISHED"}`) | `UNREGISTER_CLEAN` | module `qz_ext.qz_fx_native_repo.qz_fx_native`; `{"Operator": 1}`; compat is not activated by the loader |

Test repositories: `qz_fx_repo` → `tests/fixtures/extensions/qz_fx_repo`; `qz_fx_native_repo` →
`tests/fixtures/native/qz_fx_native_repo`; legacy add-ons directory → `tests/fixtures/addons`.

#### 3.4.9 Tests

All in `tests/addons/` (the 10 files below). Tests that touch the session use `qz`/`qz_empty`
(native) or `bpy`/`bpy_lenient` (Blender add-ons) and the local fixture `addon_env`; `bl_info`/manifest/discovery
tests use no session. Isolation before the sibling tasks (§0.6): the loader mechanics are tested with native extensions (`qz_ext.*`, no compat) written to `tmp_path`, with a
fake `quartz.compat` and a fake `smoke`; only tests that import `bpy` depend on
`l3-compat-bpy` (they pass at the L3 gate). A test under `qz` (without `bpy`) that enables a name that does **not**
start with `qz_ext.` MUST use `fake_compat` — otherwise `enable` would activate the real compat and leave it
active for the following tests (the loader never deactivates it, §3.0.4).

- `conftest.py` — fixtures (all `function`):
  - `addon_env` (uses `qz_user_dir`): saves `set(sys.modules)`, `list(sys.path)` and
    `sys.dont_write_bytecode`; sets `sys.dont_write_bytecode = True`; `MANAGER.q_reset()` on entry
    and on exit; on exit removes from `sys.modules` only the **new** keys whose first component is
    `bl_ext` or `qz_ext`, or whose module has `__file__` inside `tmp_path` or `FIXTURES_DIR`
    (NEVER `quartz`/`quartz.*` nor shims: reimporting them would break class identities and
    registrations), restores `sys.path[:]` and the flag, and calls `importlib.invalidate_caches()`.
  - `fixture_repos` (on top of `addon_env`): `quartz.app.paths.add_addon_dir(FIXTURES_DIR / "addons")`,
    `add_extension_repo("qz_fx_repo", FIXTURES_DIR / "extensions" / "qz_fx_repo")`,
    `add_extension_repo("qz_fx_native_repo", FIXTURES_DIR / "native" / "qz_fx_native_repo")`
    (undone by the `paths.reset()` of `qz_user_dir`).
  - `make_addon` (on top of `addon_env`; returns the factory `make(name: str, body: str, *, kind: str =
    "LEGACY_FILE", bl_info: dict | None = None, manifest: dict | None = None, repo: str =
    "qz_t_repo") -> str`): writes to `tmp_path` the file/package with the §0.1 header, the `bl_info`
    (literal repr, followed by a blank line) and `body`; for `EXTENSION`/`NATIVE_EXTENSION` it writes the
    TOML manifest from `manifest` (default: a valid manifest with `id = name`) in
    `tmp_path/<repo>/<name>/` and registers the repository; for legacy ones it registers `tmp_path/legacy` with
    `add_addon_dir`; calls `importlib.invalidate_caches()`; returns the module name (`name`,
    `f"bl_ext.{repo}.{name}"` or `f"qz_ext.{repo}.{name}"`). Test names start with `qz_t_`.
  - `fake_compat` (`monkeypatch`): fake module with `is_active()`, `activate(*, strict=False)` (counts
    calls; configurable to raise `CompatError`), `missing_symbols()` (returns a copy of a
    `Counter` that the test modifies) and `note_missing(s)`; installed with `monkeypatch.setitem(sys.modules,
    "quartz.compat", fake)` and `monkeypatch.setattr(quartz, "compat", fake, raising=False)`.
  - `fake_smoke`: callable `smoke(module_name) -> {"drawn": n, "failed": 0, "skipped_poll": 0}` with
    `n` = number of `Panel`/`Menu`/`Header` of the owner; attribute `fail = True` makes it return `failed=1`;
    `raises = True` makes it raise `RuntimeError("smoke")`.
- `test_bl_info.py` — `read_bl_info`: snippet from the 1st line that starts with `bl_info` to the 1st blank
  line; `bl_info` followed by code without a blank line (the exact layout of the probe add-on) →
  read; blank line inside the dict → `None` + `'could not be parsed'`; non-literal value →
  `None` + `'could not be parsed'`; no line starting with `bl_info` → `'no "bl_info" found'`;
  value that is not a `dict` → `'is not a dict'`; non-UTF-8 → `None` + `"is not UTF-8"`; BOM accepted;
  `fast=False` finds `bl_info` after blank lines; directory → `__init__.py`; the file
  contains `raise SystemExit` after the `bl_info` and nothing is executed; `problems` accumulates.
  `module_bl_info`: with the probe's `bl_info` (`"D1on1n <x@y.z>"`, `version (0, 1, 0)`, `blender (4,
  2, 0)`, `category "Development"`) the result, with tuples as lists, is **equal and in the same key order**
  as `probes.addon_lifecycle.module_bl_info` **[O]**; `name ""` → module name;
  expansion of `{BLENDER_MANUAL_URL}` to `MANUAL_URL`; `author` with two emails and spaces (rule
  `\s*<.*?>`); a second call returns the same object without changing anything; a module without `bl_info` gets one;
  `dict(BL_INFO_BASIS)` == `probes.addon_lifecycle.bl_info_basis` (tuples as lists) **[O]**.
- `test_manifest.py` — valid manifest (strict and non-strict) with all fields;
  `manifest_to_bl_info` (keys in `BL_INFO_BASIS` order, `"1.2.3-rc1"` → `(1, 2, 3)`, `category
  "Development"`, `module_bl_info` afterwards only adds `"_init"`); a manifest with several defects
  raises **one** `ManifestError` with all the problems (each fragment of the §3.4.3 table) and
  `issubclass(ManifestError, ValueError)`; `str(exc)` joins with `"; "`; `exc.path` is the file;
  2-number versions: problem in strict, accepted in non-strict; `blender_version_max = ""` →
  `None`; `permissions` as a list: problem in strict, converted in non-strict; invalid TOML →
  single problem `"invalid TOML"`; directory without a manifest → `"manifest not found"`; `wheels` and
  unknown key → `warnings`, not problems; native requires `quartz_version_min` and sets
  `native=True`; priority of `blender_manifest.toml` when given a directory; problem order
  (the 4 of `qz_fx_bad_manifest`, §3.4.8, by fragment and position).
- `test_discovery.py` — in `tmp_path`: file, package, `modules` folder, hidden folder, `__pycache__`
  and add-on without `bl_info` (listed with `bl_info None` and a problem); `path`, `kind`, `mtime`; order by
  casefold name and module; duplicate between two directories (the first wins, `duplicates` receives
  `(bl_info["name"], kept, ignored)`); extensions: module
  `bl_ext.<repo>.<folder>`/`qz_ext.<repo>.<folder>`, invalid manifest (`manifest None`, `problems`),
  no `__init__.py`, two manifests, `id` ≠ folder (warning); `include_extensions=False`; no new
  module in `sys.modules` and `sys.path` intact after `discover`; `ensure_extension_packages`
  (packages with `__path__`, package `__spec__`, attribute on the parent, idempotent, `__path__` updated in
  place, non-synthetic module preserved); `sync_sys_path` without duplicating; `locate` via `discover` and
  via `PathFinder`; `discover` over the fixtures finds the 11 targets of §3.4.8 with the `kind` from the table.
- `test_enable_disable.py` — with `qz` + `addon_env` and add-ons from `make_addon` (native extensions;
  legacy ones only with `fake_compat`): order (`default_set` before the import: the module reads
  `quartz.context.preferences.addons` at import and sees its own entry); RestrictBlend at import and
  at `register` (`quartz.data` → `RestrictedAccessError` becomes a failure; with `settings.restrict_register
  = False` it passes); `owner_scope` (`registry.classes_owned_by(name)`); return value, `__addon_enabled__`,
  `__addon_persistent__`, `__time__`; `register` called once; failure: `handle_error` receives the
  exception, module and submodules out of `sys.modules`, `default_set` undone, `None`, class
  registered before the failure remains registered; nonexistent module → `ModuleNotFoundError` with
  `'Add-on not loaded: "'` and `'", cause: '` **[O]**; default `handle_error` writes the traceback to
  `stderr`; re-enabling an enabled one calls `unregister` and `register` again, without dispatching
  `addon_disable_post`; changed `mtime` (new content and `os.utime` with +10 s) → `reload` (module
  variable reset) and `__time__` updated, unchanged → no re-execution; missing dependency
  inside the add-on → original `ModuleNotFoundError`, without `"Add-on not loaded"`; `disable`: flags,
  `unregister` once, exception from `unregister` goes to `handle_error` and does not propagate, module
  remains in `sys.modules` **[O]**; `addon_enable_post`/`addon_disable_post` with `(module_name,)`
  only in the cases of §3.4.5 (never on `enable` failure); `check` sequence **[O]**;
  `check_extension`; `disable_all` in reverse enabling order; `reset_all` (with and without
  `reload_scripts`); `paths()`; `modules()` (fake modules with `bl_info`/`__file__`/`__time__`,
  order by `(category, name)`, cache reused by `__file__`+`__time__`, `addons_fake_modules`
  mutated in place, `error_duplicates`, `error_encoding`); with `fake_compat`: name without `qz_ext.`
  calls `activate(strict=False)` once if inactive and does not call it if active, `qz_ext.` name never
  calls; `CompatError` from activation → failure without import; `quartz.compat` absent
  (`sys.modules["quartz.compat"] = None`) → proceeds with warning `"quartz.compat unavailable"`;
  `pin_annotations` via `enable` (default pinned at the end of the import even if `register()` changes the
  global before registering); `bl_ext.`/`qz_ext.` name with 2 or 4 components → `"Add-on not
  loaded"`; `extensions_refresh` with wheels keeps the warning even for a module in
  `addon_modules_pending`.
- `test_extensions.py` — with `bpy` + `fixture_repos`: `enable("bl_ext.qz_fx_repo.qz_fx_ext",
  default_set=True)`: `__package__`, own `bl_info` erased and replaced by the synthetic one,
  `prefs.addons[name].preferences` is `QzFxExtPrefs` **[O]**, `check_extension` true,
  `bpy.utils.extension_path_user(__package__)` points to `.user/qz_fx_repo/qz_fx_ext`; `disable`;
  invalid manifest → `handle_error` with `ManifestError` and the module never imported; with `qz` (without
  `bpy`): native extension enables without activating compat (`quartz.compat` does not enter `sys.modules`
  if it was not there; if it was, `is_active()` remains false), registers and unregisters cleanly;
  `quartz_version_min` above `quartz.app.version` → `"requires Quartz"`; `type "theme"` →
  `'"theme" cannot be enabled'`; unknown repository → `"Add-on not loaded"`;
  `extensions_refresh` with `wheels` → warning in `q_warnings`, `sys.path` unchanged,
  `addon_modules_pending` enabled.
- `test_report_leaks.py` — `enable_with_report` with native add-ons in `tmp_path` and `fake_smoke`:
  each level (`NONE` for nonexistent target and for missing metadata, `METADATA` for import failure,
  `IMPORT` for `register` failure, `REGISTER` for `smoke` with `failed=1`, `UI_SMOKE` for leak,
  `UNREGISTER_CLEAN`), `keep_enabled`, `smoke=None` (warning `"UI smoke skipped"`); `registered`,
  `type_props_added`, `menus_extended`, `handlers_added`; `leaks` in the four formats and in the order of
  §3.4.5 (forgotten class, prop on `quartz.types.Scene` not removed, function appended to a
  `Menu` subclass registered by the test itself outside the owner and not removed, handler of
  `quartz.app.handlers.load_post` not removed); add-on without leaks → `[]`; `smoke` that raises →
  `error_type "RuntimeError"`, level `REGISTER` and add-on disabled; `pin_annotations`: count,
  warning for `NameError`, and, on a class without `from __future__ import annotations`,
  `"__annotations__" not in cls.__dict__` and `cls.__annotate__` the same object after pinning;
  `missing_symbols` as a delta with `fake_compat`; `to_dict()` passes through `json.dumps` and has
  `registered_counts`; `AddonReport` with invalid `reached` → `ValueError`.
- `test_fixture_levels.py` — parametrized by the 10 Blender targets of §3.4.8, with `bpy_lenient` +
  `fixture_repos`: `MANAGER.enable_with_report(name, smoke=fake_smoke)` reaches the level from the table
  (`STATIC` → `"NONE"`), `to_dict()["registered_counts"]` and the effects in the last column;
  `qz_fx_future` with `keep_enabled=True` registers with default `2`. A separate test, with `qz`
  (without `bpy`) + `fixture_repos`, does the same for `qz_ext.qz_fx_native_repo.qz_fx_native` and checks
  that compat was not activated.
- `test_addon_utils_shim.py` — with `bpy`: `import addon_utils` comes from `compat_dir()`; each function is
  the same object as in `quartz.addons`; `addon_utils.addons_fake_modules is
  MANAGER.addons_fake_modules`; `error_duplicates` likewise; `error_encoding` follows
  `MANAGER.error_encoding`; public names of `dir(addon_utils)` == the 16 from the dump **[O]**;
  `stale_pending_*` return `None` with no effect; `addon_utils.qz_nope` → `AttributeError` with
  `"module 'addon_utils' has no attribute 'qz_nope'"` and `"addon_utils.qz_nope"` noted
  (`missing_symbols()`), `addon_utils._qz_nope` → `AttributeError` without noting; the file does not import numpy nor use `from
  __future__` (`ast` analysis) and only defines non-re-exported functions for the two no-ops.
- `test_contract_addon_lifecycle.py` — reproduces the `probes.addon_lifecycle` probe with `bpy`: writes to
  `tmp_path` the probe add-on with the same layout (`quartz_probe_addon`; multi-line `bl_info`
  followed directly by `import bpy`, without a blank line; author with email;
  `QuartzProbePrefs(AddonPreferences)` with `bl_idname = __name__` and `flag:
  BoolProperty(default=True)`, `LOG`), adds the directory with `quartz.app.paths.add_addon_dir`,
  calls `enable`/`disable` with `default_set=True, refresh_handled=True` like the probe and compares with the
  dump, key by key: `check_before`, `enable_returns_module`, `module_flags`, `log_after_enable ==
  ["register"]`, `check_after_enable`, `in_preferences_addons`, `prefs_type == "QuartzProbePrefs"`,
  `prefs_flag`, `module_bl_info` (order included), `log_after_disable`, `check_after_disable`,
  `still_in_sys_modules`, `missing_error` (type `ModuleNotFoundError` and the fragments `'Add-on not
  loaded: "quartz_no_such_addon", cause: '` and `"No module named 'quartz_no_such_addon'"`),
  `enable_missing_returns == "None"`, `addon_utils_public`, `bl_info_basis`, `ext_base_pkg ==
  EXT_BASE_PKG`, `ext_manifest_filename == BLENDER_MANIFEST` — all **[O]**; and, as a declared
  divergence, the default repositories of `quartz.app.paths.extension_repos()` are `{"user_default",
  "system"}` (without the remote `blender_org` from the dump).

### 3.5 CLI, sweep, scan and goldens (`l3-cli-sweep`)

This task delivers the `python -m quartz` entry point (five subcommands), the sweep harness
(levels from §3.0.5, isolated execution from §3.0.6, Blender baseline and ratchet), the in-house static scanner,
the symmetric goldens runner, the script fixtures, the `README.md` and `docs/ROADMAP.md`.
It consumes all L2 and L3 tasks (§0.6), always through the names published in §0–§3; it does not define
new `quartz.errors` classes (it consumes `ManifestError` through `quartz.addons`).

General rules of the task:

1. **No import side effects** (§3.0.2): at module level, `quartz.cli`, `quartz.sweep` and
   `quartz.scan` import only stdlib, L1/L2 modules and each other (`cli` → `sweep`, `scan`;
   `sweep` → `scan`). Every import of `quartz.compat`, `quartz.addons`, `quartz.extras` and
   `quartz.bmesh` is done **inside functions**. `import quartz.cli` works even if these sibling modules
   do not exist yet.
2. **Missing sibling**: where this section says "if available", the code calls `importlib.import_module(name)`
   and treats a `ModuleNotFoundError` whose `.name` is the module itself (or a parent of it) as absence; any other
   error propagates (same rule as `load_builtin_types`, §2.2.1).
3. **Disk writes** only under `quartz.app.paths.PROJECT_ROOT` (§0.1(5)): every output path
   received by the CLI (`addon-sweep --json OUTPUT`, `--md`, `--work-dir`, `--ratchet` with
   `--update-ratchet`) whose `Path(p).resolve()` does not satisfy `.is_relative_to(PROJECT_ROOT.resolve())`
   → code `2` with `"outside the project root"`. Paths that are only read (Blender corpus) MAY be
   outside.
4. Human output in English; JSON with English keys, `sort_keys=True`, `indent=2`,
   `ensure_ascii=False`, terminated by `"\n"` (ARCHITECTURE §10). Human text MUST be encodable in
   cp1252 (no arrows, emoji or box characters).
5. Determinism: no output has a timestamp; lists of targets, symbols and keys come out in
   the order defined in this section. Only the `seconds` fields depend on the clock (measurement).

#### 3.5.1 `quartz/cli.py`

```python
EXIT_OK: int = 0; EXIT_FAILURE: int = 1; EXIT_USAGE: int = 2; EXIT_INTERNAL: int = 3
def main(argv: Sequence[str] | None = None) -> int     # None -> sys.argv[1:]; never raises (except KeyboardInterrupt)
def build_parser() -> argparse.ArgumentParser          # prog="quartz"; required subparsers
def cmd_info(args: argparse.Namespace) -> int
def cmd_scan_addon(args: argparse.Namespace) -> int
def cmd_enable_addon(args: argparse.Namespace) -> int
def cmd_run_script(args: argparse.Namespace) -> int
def cmd_addon_sweep(args: argparse.Namespace) -> int
```

Command line (exact options; `...` = repeatable; `--version` at the top level):

```
quartz --version                                     # prints "quartz 0.1.0"; code 0
quartz info [--json]
quartz scan-addon TARGET [--json]
quartz enable-addon MOD|PATH [--path DIR]... [--repo NAME=DIR]... [--no-restrict] [--strict]
                    [--smoke-ui] [--keep-enabled] [--json] [--sweep-mode]
quartz run-script FILE.py [--empty] [--no-compat] [--strict] [--addon MOD]... [--json] [--sweep-mode] [-- ARGS...]
quartz addon-sweep [--blender-scripts DIR] [--fixtures] [--no-templates] [--only NAME]... [--jobs N]
                   [--timeout S] [--json OUTPUT] [--md OUTPUT] [--baseline FILE] [--ratchet FILE]
                   [--update-ratchet] [--work-dir DIR]
```

`run-script --json`, `run-script --sweep-mode` and `addon-sweep --work-dir` are additions of this
section (used by the sweep and by the tests). In `addon-sweep`, `--json` takes a path; in the other
subcommands it is a flag (JSON on `stdout`). Splitting off `ARGS`: if the token `run-script` appears
in `argv` before the first `"--"`, `main` cuts `argv` at that `"--"` before argparse; everything after
it becomes `args.script_args` (list, possibly empty) without interpretation. In the other subcommands
`"--"` goes to argparse as usual.

**Sequence of `main(argv)`** (the order is normative):

1. `parser.parse_args(argv)`; argparse's `SystemExit` is caught: code `0` (`--help`,
   `--version`) → `EXIT_OK`; any other → `EXIT_USAGE` (the argparse message has already gone to
   `stderr`). No subcommand → help on `stderr` and `EXIT_USAGE`. No global state is touched before
   this step.
2. Semantic validation of the options (see each subcommand) → `EXIT_USAGE` with an English message on
   `stderr`, still without a session.
3. Save, to restore in step 10: `quartz.app.settings.snapshot()`, `sys.argv` (copy),
   `sys.dont_write_bytecode`, `quartz.compat.is_active()`/`is_strict()` (if available) and the
   `errors` attribute of `sys.stdout`/`sys.stderr`; then each of these two streams receives
   `reconfigure(errors="replace")` when the object has that method. Steps 3–11 run inside
   `try`/`finally`: steps 9–11 happen even after an error.
4. Network: if `args.sweep_mode` (only `enable-addon`/`run-script` have the option) →
   `quartz.app.settings.settings.sweep_mode = True`; if `settings.sweep_mode` is true at this point
   (by the option or because it already was), steps 5–9 run inside `quartz.sweep.network_guard()`
   (§3.0.6(3)). `enable-addon` and `run-script` (with or without `--sweep-mode`) set
   `sys.dont_write_bytecode = True` until step 10.
5. L3 adapters (§3.0.2): `quartz.extras.install_adapters()` and `quartz.bmesh.install_adapters()`,
   each if available.
6. `s = quartz.session.current()`; in `run-script`: `quartz.session.reset(template="empty" if
   args.empty else "default")` (new scene on every run, even in-process; `reset` clears
   non-persistent handlers, §2.1.2).
7. `quartz.app.handlers.dispatch("startup_post")` (§2.1.2: `quartz.cli.main` is the only
   dispatcher of the three phases).
8. Runs `cmd_<sub>(args)`. In `enable-addon` and `run-script` with `--json`, the entire body of the
   command runs under `contextlib.redirect_stdout(sys.stderr)`, and only the final JSON document is written
   to the original `stdout`; this way `stdout` contains **only** that document, even if the add-on or the script
   prints. An exception (`Exception` or `SystemExit`) that escapes from `cmd_*` or from steps 4–7 (a Quartz
   defect, not a defect in the user's code) → traceback on `stderr`, line `"internal error: <type>:
   <message>"`, code `EXIT_INTERNAL`. `KeyboardInterrupt` propagates (after the `finally`).
9. `dispatch("shutdown_pre")` (whenever step 7 happened, including after an internal error).
10. Cleanup: leaves the `network_guard`; compat: if `main` activated it (it was inactive in step 3 and is
    active now, whoever activated it) → `quartz.compat.deactivate()`; if it was active with
    a different strictness → `activate(strict=<the previous one>)`; `quartz.app.settings.restore(<snapshot>)`;
    `sys.argv[:]`, `sys.dont_write_bytecode` and the `errors` of the two streams restored. The
    adapters installed in step 5 are NOT undone by `main` (only by `deactivate`, by leaving
    `quartz.testing.isolated`, or by the end of the process); `quartz.app.paths` (add-on directories and
    added repositories) is not restored either (in tests, `qz_user_dir` calls
    `paths.reset()`).
11. `dispatch("shutdown_post")`; returns the command's code.

Exit codes: `0` success; `1` operation failure (target below the maximum level, script that
failed, invalid metadata, ratchet regression, no target); `2` usage error (invalid option,
nonexistent file/target, output outside the root); `3` internal error.

**`info`** — never activates compat; code `0`. JSON (exact keys):

```python
{"quartz": {"version": __version__, "author": AUTHOR}, "python": platform.python_version(),
 "numpy": numpy.__version__, "platform": sys.platform,
 "paths": {"project_root": str, "user_dir": str, "compat_dir": str, "addon_dirs": [str, ...],
           "extension_repos": {name: str}},
 "compat": {"available": bool, "active": bool, "blender_version": "5.2.2 LTS" | None},  # profile().version_string if available
 "registry": {"by_base": registry.counts_by_base(), "builtin_operators": int,           # sum(1 for _, c in registry.iter_operators() if quartz.operators.is_builtin(c))
              "operator_submodules": registry.operator_submodules()},
 "session": {"template": s.template, "filepath": s.data.filepath, "scenes": int, "objects": int, "meshes": int},
 "handlers": {"blender": len(BLENDER_HANDLER_NAMES), "quartz": len(QUARTZ_HANDLER_NAMES)}}
```

`compat.available` = `quartz.compat` importable (rule 2); `active` = `quartz.compat.is_active()`
(`False` if unavailable); `blender_version` = `quartz.compat.profile().version_string` (`"5.2.2
LTS"` **[O]**, `None` if unavailable); none of these accesses activates compat. `scenes`/`objects`/
`meshes` = `len(s.data.scenes)`/`len(s.data.objects)`/`len(s.data.meshes)`.

Text: one line per group, starting with `f"{APP_NAME} {__version__} (author: {AUTHOR})"` (=
`"Quartz 0.1.0 (author: D1on1n)"`); contains `"Python"`,
`"numpy"`, `"User directory:"`, `"Compat:"` (`"available"`/`"unavailable"`, Blender
version and `"active"`/`"inactive"`), `"Built-in operators:"` and `"Session:"`.

**`scan-addon TARGET`** — `TARGET` is a `.py` file, a package (folder with `__init__.py`), an
extension folder (with `blender_manifest.toml` or `quartz_manifest.toml`) or any folder of `.py` files.
Nonexistent → `2` with `"not found"`. Calls `quartz.scan.scan_path(TARGET)` (with prediction, which
needs the session from step 6); `--json` prints `ScanResult.to_dict()`. Code `0` if the target
would statically reach `METADATA` (`parse_errors` empty and (`bl_info is not None` or
(`manifest is not None` and `manifest_problems` empty))); otherwise `1`. Never imports the scanned code.
Text: `"Target:"`, `"Files:"` (with `"syntax errors"`), `"bl_info:"` (`"present"`/`"absent"`),
`"Manifest:"`, `"Distinct symbols:"`, `"Predicted as ghost:"` and `"Predicted as missing:"`
followed by the lists.

**`enable-addon MOD|PATH`** — one full cycle of §3.0.5 in-process:

1. Each `--path DIR` → `quartz.app.paths.add_addon_dir(DIR)` (nonexistent `DIR` → `2` with `"not
   found"`); each `--repo NAME=DIR` → `add_extension_repo(NAME, DIR)` (no `"="`, empty
   parts or `ValueError` from L1 → `2` with `"invalid --repo"`). `--no-restrict` →
   `quartz.app.settings.settings.restrict_register = False` (restored in step 10 of `main`).
2. Target: if the argument is an existing path → `quartz.sweep.target_from_path(arg)` (`ValueError` →
   `2` with `"not an add-on"`); otherwise looks for the first `info` with `info.module_name == arg` in
   `quartz.addons.discover()` and converts it: `path` = `info.path.parent` if `info.path.name ==
   "__init__.py"`, otherwise `info.path` (resolved); `name` = last component of `module_name`;
   `kind` = `info.kind`; `search_path` = `path.parent`; `repo` = `info.repo`. Not found → `2` with
   `"add-on not found"`.
3. `r = quartz.sweep.run_target_inprocess(target, smoke_ui=args.smoke_ui, strict=args.strict,
   keep_enabled=args.keep_enabled)` (without `--smoke-ui` the UI smoke is skipped and `UI_SMOKE` counts as
   reached, §3.4.5).
4. `--json` → `r.to_dict()`; text → `"Target: {name} ({kind})"`, `"Level: {level}"` + `"ok"`/`"failed"`,
   `"Registered classes:"`, `"Extended menus:"`, `"UI smoke:"`, `"Leaks:"`,
   `"Missing symbols:"`, `"Error:"` (when there is one). Code `0` if `r.ok`, otherwise `1`.

**`run-script FILE.py`** — headless equivalent of `blender --background --python FILE -- ARGS`:

1. `FILE` nonexistent or without a `.py` suffix → `2` with `"not found"` (checked in step 2 of
   `main`, before the session).
2. Without `--no-compat`: `quartz.compat.activate(strict=args.strict)` (lenient default, ARCHITECTURE
   §16, item 3); compat unavailable → warning on `stderr` and proceeds without compat.
3. Each `--addon MOD` (in order) → `quartz.addons.MANAGER.enable(MOD, default_set=True,
   handle_error=<records>)`; return `None` → traceback on `stderr`, `"add-on not enabled: {MOD}"`,
   code `1` without running the script.
4. Without `--json`: `out = quartz.sweep.exec_script(FILE, args.script_args)`; returns
   `out.exit_code` (`0` or `1`).
5. With `--json`: `r = run_target_inprocess(Target(name=Path(FILE).stem, kind="SCRIPT",
   path=Path(FILE).resolve()), strict=args.strict, argv=args.script_args, use_compat=not
   args.no_compat)`; prints `r.to_dict()`; code `0` if `r.ok`, otherwise `1`.

The script's directory does NOT go into `sys.path` **[I]** (Blender does not insert it for `--python`).

**`addon-sweep`** — orchestrator (each target runs in a subprocess, §3.0.6):

1. Validation (`2`): `--jobs` < 1, `--timeout` <= 0, outputs outside the root.
2. Targets: the corpus is included if `--blender-scripts` was given **or** `--fixtures` was not given (root =
   `--blender-scripts` or `DEFAULT_BLENDER_SCRIPTS`); corpus root missing with the corpus requested → `2`
   with `"Blender scripts directory not found"` (an existing folder with neither `addons_core` nor
   `templates_py` is not a usage error: it yields zero targets). Corpus →
   `discover_blender_targets(root, templates=not args.no_templates)`; `--fixtures` appends
   `discover_fixture_targets()` afterwards. `--only NAME` filters by `Target.name`; a name that is not
   among the discovered ones → `2` with `"unknown target in --only"`. Empty final list → `1` with
   `"no target"`.
3. `report = quartz.sweep.sweep(targets, jobs=args.jobs, timeout=args.timeout,
   work_dir=args.work_dir)`.
4. `baseline = load_baseline(args.baseline)`; `ratchet = load_ratchet(args.ratchet)`;
   `regs = report.check_ratchet(ratchet)`.
5. `--json OUTPUT` → `report.to_json(baseline=baseline, ratchet=ratchet)`; `--md OUTPUT` →
   `report.to_markdown(baseline=baseline, ratchet=ratchet)` (UTF-8, folders created). Without these
   options nothing is written.
6. `--update-ratchet` → `update_ratchet(report, args.ratchet)` (after step 4).
7. Text on `stdout`: one line per target `f"{level:<16} {name}"`, then `"Targets: N"`, count per
   level, `"Green (= Blender): G of T"` when there is a baseline and, if there are regressions, `"ratchet
   regression:"` followed by each message. Code `1` if `regs` is not empty, otherwise `0`.

Errors verified by test: exit codes and the English fragments cited above, on `stderr`
(exception: the `addon-sweep` report lines, including `"ratchet regression"`, go to
`stdout`).

#### 3.5.2 `quartz/sweep.py`

```python
LEVELS: tuple[str, ...] = ("NONE", "STATIC", "METADATA", "IMPORT", "REGISTER", "UI_SMOKE", "UNREGISTER_CLEAN")
TARGET_KINDS: tuple[str, ...] = ("LEGACY_FILE", "LEGACY_PACKAGE", "EXTENSION", "NATIVE_EXTENSION", "SCRIPT")
DEFAULT_BLENDER_SCRIPTS: Path   # env QUARTZ_BLENDER_SCRIPTS or "C:/Program Files/Blender Foundation/Blender 5.2/5.2/scripts"
                                # (computed at import, same rule as BLENDER_SCRIPTS in §1.1.2; reading the env is not a side effect)
DEFAULT_BASELINE_PATH: Path     # PROJECT_ROOT/"data"/"sweep"/"blender_baseline.json"
DEFAULT_RATCHET_PATH: Path      # PROJECT_ROOT/"data"/"sweep"/"ratchet.json"
DEFAULT_WORK_DIR: Path          # PROJECT_ROOT/"tmp"/"sweep"
BOOT: str   # "import sys; sys.dont_write_bytecode = True; sys.path.insert(0, <repr(str(PROJECT_ROOT))>); "
            # "import quartz.cli; raise SystemExit(quartz.cli.main(sys.argv[1:]))"
def level_index(level: str) -> int                    # LEVELS.index; other -> ValueError("unknown sweep level: ...")
def max_level(kind: str, *, keep_enabled: bool = False) -> str
    # "SCRIPT" -> "IMPORT"; keep_enabled -> "UI_SMOKE"; others -> "UNREGISTER_CLEAN"
@dataclass
class Target:
    name: str; kind: str; path: Path; search_path: Path | None = None; repo: str | None = None
def module_name_for(target: Target) -> str
    # LEGACY_* -> name; EXTENSION -> f"bl_ext.{repo}.{name}"; NATIVE_EXTENSION -> f"qz_ext.{repo}.{name}";
    # SCRIPT -> ValueError("script targets have no module name"); kind not in TARGET_KINDS -> ValueError("unknown target kind: ...")
def target_from_path(path: str | Path) -> Target
@dataclass
class SweepResult:
    target: str; kind: str; level: str; ok: bool; registered: dict[str, int]; menus_extended: list[str]
    ui_smoke: dict[str, int]; missing_symbols: dict[str, int]; warnings: list[str]; leaks: list[str]
    error_type: str | None; error: str | None; traceback_tail: str | None; seconds: float
    def to_dict(self) -> dict                          # all keys = field names; dicts with sorted keys
    @classmethod
    def from_dict(cls, d: Mapping) -> "SweepResult"
        # requires target/kind/level (level ∈ LEVELS); absent ones: ok False, dicts {}, lists [], texts None, seconds 0.0; extra key ignored
@dataclass
class SweepReport:
    results: list[SweepResult]; seconds: float
    def missing_symbol_ranking(self) -> list[tuple[str, int, list[str]]]
    def compare_baseline(self, baseline: Mapping[str, object]) -> dict[str, object]
    def check_ratchet(self, ratchet: Mapping[str, str]) -> list[str]
    def to_json(self, *, baseline: Mapping[str, object] | None = None, ratchet: Mapping[str, str] | None = None) -> dict
    def to_markdown(self, *, baseline: Mapping[str, object] | None = None, ratchet: Mapping[str, str] | None = None) -> str
def discover_blender_targets(scripts_root: str | Path, *, addons: bool = True, templates: bool = True) -> list[Target]
def discover_fixture_targets(root: str | Path | None = None) -> list[Target]   # None -> PROJECT_ROOT/"tests"/"fixtures"
def ui_smoke(module_name: str) -> dict[str, int]      # {"drawn", "failed", "skipped_poll"}
@dataclass
class ScriptOutcome:
    exit_code: int; error_type: str | None; error: str | None; traceback: str | None
def exec_script(path: str | Path, argv: Sequence[str] = ()) -> ScriptOutcome    # never raises (except KeyboardInterrupt)
def run_target_inprocess(target: Target, *, smoke_ui: bool = True, strict: bool = False, keep_enabled: bool = False,
                         argv: Sequence[str] = (), use_compat: bool = True) -> SweepResult   # never raises (except KeyboardInterrupt)
def boot_command(args: Sequence[str]) -> list[str]    # [sys.executable, "-I", "-B", "-X", "utf8", "-c", BOOT, *args]
def run_target(target: Target, *, timeout: float = 60.0, work_dir: str | Path | None = None) -> SweepResult
def sweep(targets: Sequence[Target], *, jobs: int = 1, timeout: float = 60.0, work_dir: str | Path | None = None) -> SweepReport
@contextmanager
def network_guard() -> Iterator[None]
def load_baseline(path: str | Path | None = None) -> dict
def load_ratchet(path: str | Path | None = None) -> dict
def update_ratchet(report: SweepReport, path: str | Path | None = None) -> dict
```

**Absolute paths**: every `Target` produced by this section (`target_from_path`,
`discover_*`, CLI conversion) has absolute `path` and `search_path` (`Path.resolve()`), because the
subprocess runs with a different `cwd`.

**`target_from_path(path)`** (the path is resolved; rules tested in this order): file
`__init__.py` → handles the parent folder; file `*.py` → `LEGACY_FILE`, `name` = `stem`, `search_path` =
parent folder; folder with `blender_manifest.toml` → `EXTENSION`, `name` = folder name, `repo` = name of the
parent folder, `search_path` = parent folder; folder with `quartz_manifest.toml` → `NATIVE_EXTENSION` (same
rules); folder with `__init__.py` → `LEGACY_PACKAGE`, `name` = folder name, `search_path` =
parent folder; any other case, or a `repo` that is not a Python identifier → `ValueError` with `"not an add-on"`.
Never returns `SCRIPT`. Invariant (used by the subprocess, which receives only the path): for every
non-`SCRIPT` target `t` returned by `discover_blender_targets`/`discover_fixture_targets`,
`target_from_path(t.path) == t`.

**Discovery.**

- `discover_blender_targets(root)`: nonexistent root → `FileNotFoundError` with `"Blender scripts
  directory not found"`. Add-ons: `quartz.path.module_names(str(root/"addons_core"))` (excludes
  `modules`); file → `LEGACY_FILE` (`path` = the file), package → `LEGACY_PACKAGE` (`path` = the
  folder); `search_path` = `addons_core`; order of `module_names`. Templates: each `*.py` of
  `root/"templates_py"` (recursive, without `__pycache__`), sorted by POSIX relative path,
  `Target(name=f"templates_py/{rel without .py}", kind="SCRIPT", path=file)`. Add-ons before the
  templates; missing subfolder → no targets from it. In Blender 5.2.2: 13 add-ons and 38 templates **[O]**
  (`data/bpy_usage.json` `population`); `startup/bl_operators` is not a target.
- `discover_fixture_targets(root)`: `root/"addons"` via `module_names` (`LEGACY_*` with the same
  `path`/`name` rules as the corpus add-ons, `search_path` = `root/"addons"`); each
  `root/"extensions"/<repo>/<pkg>/` with `blender_manifest.toml` → `EXTENSION`; each
  `root/"native"/<repo>/<pkg>/` with `quartz_manifest.toml` → `NATIVE_EXTENSION` (`name` = `<pkg>`,
  `repo` = `<repo>`, `path` = the package folder, `search_path` = repo folder); each
  `root/"scripts"/*.py` → `SCRIPT` (`name` = `stem`). Order: add-ons, extensions, native ones, scripts;
  within each group by `name`. With the fixtures of §3.4.8 and §3.5.6: 15 targets (8 add-ons, 2
  extensions, 1 native, 4 scripts).

**`exec_script(path, argv)`**: sets `sys.argv = [str(path)] + (["--", *argv] if argv else [])`
**[I]** (Blender scripts read what comes after `"--"`); `runpy.run_path(str(path),
run_name="__main__")`; always restores `sys.argv`. Normal end → `exit_code 0`. `SystemExit` with
code `None`/`0` → `0`; any other code → `1` with `error_type "SystemExit"` and `error` = `str(code)`.
`SystemExit` with a non-integer code (e.g. text) → `1`, `error` = `str(code)`. `Exception` →
full traceback on `stderr`, `exit_code 1`, `error_type` = class name, `error` = `str(exc)`,
`traceback` = traceback text. Success: `error_type`/`error`/`traceback` `None`. The script's
directory does not go into `sys.path`. Does not activate compat or create a session (the caller does that).

**`run_target_inprocess(target, ...)`** (composes the `SweepResult`; `seconds` =
`time.perf_counter()` from start to end; an unexpected `Exception`/`SystemExit` at any step →
level = the last one reached, `error_type`/`error`/`traceback_tail` filled in; never raises):

1. **STATIC**: `quartz.scan.scan_path(target.path, predict_missing=False)`; non-empty `parse_errors`
   → level `NONE`, `error_type "SyntaxError"`, `error` = first error. Otherwise `STATIC`.
2. **METADATA**: `SCRIPT` → vacuously passed; `LEGACY_*` → `scan.bl_info is not None` (otherwise
   `error_type "ManifestError"` and `error 'no "bl_info" found'`, the same labels as the loader's report,
   §3.4.5); `EXTENSION`/`NATIVE_EXTENSION` →
   `scan.manifest is not None` and `scan.manifest_problems` empty (otherwise `error_type
   "ManifestError"`, `error` = problems joined by `"; "` (or `"manifest not found"`), problems
   also in `warnings`). Failure → final level `STATIC`.
3. Paths: `LEGACY_*` → `quartz.app.paths.add_addon_dir(target.search_path)`; extensions →
   `add_extension_repo(target.repo, target.search_path)`.
4. Compat: `use_compat` and `kind != "NATIVE_EXTENSION"` → `quartz.compat.activate(strict=strict)` and
   `quartz.compat.clear_missing()` (if available). `NATIVE_EXTENSION` never activates compat.
5. **SCRIPT**: `before = registry.counts_by_base()`; `out = exec_script(target.path, argv)`;
   `registered` = positive difference `counts_by_base() - before` (only bases with delta > 0);
   `missing_symbols` = `dict(quartz.compat.missing_symbols())` if compat is active; success →
   `IMPORT`, failure → `METADATA` with the error from `out` and `traceback_tail` = last 20 lines. End.
6. **Add-ons**: `report = quartz.addons.MANAGER.enable_with_report(module_name_for(target),
   smoke=ui_smoke if smoke_ui else None, keep_enabled=keep_enabled)` (with `None`, the report has
   `ui_smoke == {}`, the warning `"UI smoke skipped"` and counts `UI_SMOKE` as reached, §3.4.5). Level
   = `"STATIC"` if `report.reached == "NONE"`, otherwise `report.reached`.
   `registered` = count of `report.registered` by `RegisteredItem.base`; `menus_extended`,
   `ui_smoke`, `leaks`, `missing_symbols` come from the report; `warnings` = the sweep's + the
   report's; `error_type`/`error` from the report; `traceback_tail` = last 20 lines of
   `report.traceback`.
7. `ok = level == max_level(target.kind, keep_enabled=keep_enabled)`.

Disabling and cleaning up the add-on is the responsibility of `enable_with_report` (§3.4.5); `sys.modules`,
`sys.path` and the compat state are left as the manager leaves them (in production each target has its
own process).

**`ui_smoke(module_name)`**: classes = `registry.classes_owned_by(module_name)` that are subclasses
of `Panel`, `Menu` or `Header` (`quartz.types.ui`), in registration order, followed by the classes of
`quartz.types.ui.draw_funcs_owned_by(module_name)` (extended menus, in the order of the first function
appended), without repetition. For each one, `d = quartz.ui.draw_ui(cls, check_poll=True)`, in this order:
`not d.ok` → `failed` (includes `POLL_EXCEPTION`, which also makes `poll` false); otherwise `d.poll is False`
→ `skipped_poll`; otherwise `drawn`. `UIList` subclasses of the owner (§3.0.5
includes them) go into the same list, after the panels/menus/headers, and are drawn with
`quartz.ui.draw_ui_list(cls, types.SimpleNamespace(q_smoke_items=[]), "q_smoke_items")` **[I]**: the
`data` is not a `Struct`, so the property is refused (`UNKNOWN_PROPERTY`, which does not affect `d.ok`) and
the UIList is only instantiated (early return of §2.5.6, rule 7); `filter_items`, `draw_item` and
`draw_filter` do not run in the smoke. `not d.ok` (only `DRAW_EXCEPTION`) → `failed`, otherwise `drawn`. An exception coming from `draw_ui`/`draw_ui_list` (should not occur) counts as `failed`.
Never raises. `UI_SMOKE` is reached when `failed == 0` (decided by `enable_with_report`).

**Isolated execution** (§3.0.6): `run_target(target, timeout, work_dir)`:

1. `wd = Path(work_dir or DEFAULT_WORK_DIR)`; `safe` = `target.name` with every character outside
   `[A-Za-z0-9_.-]` replaced by `_`; creates `wd/"cwd"` and `wd/"user"/safe`.
2. Arguments: add-on target → `["enable-addon", str(target.path), "--json", "--sweep-mode",
   "--smoke-ui"]`; `SCRIPT` → `["run-script", str(target.path), "--json", "--sweep-mode"]`.
3. `subprocess.run(boot_command(args), cwd=wd/"cwd", env=env, capture_output=True, timeout=timeout,
   text=True, encoding="utf-8", errors="replace")`, with `env` = copy of `os.environ` +
   `QUARTZ_USER_DIR=str(wd/"user"/safe)` (`-I` ignores `PYTHON*` variables; the UTF-8 encoding of the
   streams comes from `-X utf8`).
4. Code `0` or `1` with a `stdout` that is a JSON object (`json.loads(stdout)` is a `dict`) →
   `SweepResult.from_dict`, overwriting `target = target.name` and `kind = target.kind`. `subprocess.TimeoutExpired` → level `NONE`,
   `ok=False`, `error_type "TimeoutExpired"`, `error` with `f"timeout after {timeout} s"`. Any other
   code, or a `stdout` that does not decode → level `NONE`, `error_type "SubprocessError"`, `error` with
   the exit code, `traceback_tail` = last 20 lines of `stderr`.
5. `seconds` = wall-clock time measured in the parent.

`sweep(targets, jobs, timeout, work_dir)`: `jobs == 1` → sequential; otherwise
`concurrent.futures.ThreadPoolExecutor(max_workers=jobs)` calling `run_target`; `results` in
**input order** (not completion order); `seconds` = total.

**`network_guard()`**: replaces `socket.socket.connect`, `socket.socket.connect_ex` and
`socket.create_connection` with functions that raise `PermissionError` with `"network access is
blocked in sweep mode"`; restores the originals on exit (also on exception); nested → only the outermost
swaps and restores.

**Report.**

- `missing_symbol_ranking()`: for each symbol present in any `missing_symbols`:
  `(symbol, number of targets that noted it, sorted names of those targets)`; order: count
  descending, then symbol. It is the backlog (D18).
- `compare_baseline(baseline)`: `baseline` in the format of §3.5.5 (`{}` = no baseline). For each
  result: target absent from `baseline["targets"]` → `missing_in_baseline`; different levels →
  `behind` (Quartz below) or `ahead`, with `{"target", "quartz", "blender"}` (levels); equal levels and
  equal `registered` (zero entries ignored) → `green`; equal levels and different counts →
  `count_mismatch` with `{"target", "quartz", "blender"}` (dicts). Quartz level compared: the
  result's `level`, except that a result with `level == "UI_SMOKE"`, `error_type is None` and a
  non-empty `leaks` whose items all start with `"menu "` is compared as `"UNREGISTER_CLEAN"`
  when the target's baseline is `"UNREGISTER_CLEAN"` (the baseline does not measure menu functions, §3.5.5); the
  `level` recorded in the result does not change. Returns `{"green": [...],
  "behind": [...], "ahead": [...], "count_mismatch": [...], "missing_in_baseline": [...],
  "summary": {"total", "green", "behind", "ahead", "count_mismatch", "missing_in_baseline"}}`, lists
  sorted by target; `total` = results compared (excluding `missing_in_baseline`). "Green" =
  §3.0.5.
- `check_ratchet(ratchet)`: only targets present in the report **and** in the ratchet; `level_index(current) <
  level_index(ratchet[target])` → `f"{target}: {ratchet[target]} -> {current}"`; sorted list.
- `to_json(...)`: `{"format": "quartz.sweep", "format_version": 1, "quartz_version": __version__,
  "seconds": ..., "levels": {level: count for each of LEVELS}, "results": [r.to_dict()...],
  "missing_symbol_ranking": [[symbol, n, [targets]], ...]}` + `"baseline": compare_baseline(...)`
  when `baseline` is non-empty + `"ratchet_regressions": check_ratchet(...)` when `ratchet` is non-empty.
- `to_markdown(...)`: English, in this order: `# Quartz Sweep Report`; `## Summary` (targets, by
  level, time); `## Targets` (table `| Target | Kind | Level | OK | Registered | Missing | Error |`, in
  the order of `results`); `## Comparison with Blender` (only with a baseline); `## Ratchet` (only with a
  ratchet: regressions or `"No regressions."`); `## Missing symbols` (the first 50 of the
  ranking). Same input → same text, except for the times.

**Data files**: `load_baseline(None)` reads `DEFAULT_BASELINE_PATH`; missing file → `{}`;
`"format"` different from `"quartz.sweep.baseline"` → `ValueError` with `"not a sweep baseline"`.
`load_ratchet(None)` reads `DEFAULT_RATCHET_PATH`: a flat JSON object `{target: level}`; missing → `{}`;
a document that is not a JSON object → `ValueError` with `"not a sweep ratchet"`; level outside `LEVELS` →
`ValueError` with `"unknown sweep level"`. Both readers use UTF-8. `update_ratchet(report, path)`:
starts from `load_ratchet(path)`; for each result, writes the level if the target is new or the level went up
(**never** goes down); writes JSON with sorted keys, `indent=2`, a trailing `"\n"`, UTF-8; creates the folder;
returns the dictionary that was written.

Verified errors: `ValueError` (`"unknown sweep level"`, `"not an add-on"`, `"not a sweep
baseline"`, `"not a sweep ratchet"`, `"script targets have no module name"`), `FileNotFoundError`
(`"Blender scripts directory not found"`), `PermissionError` (`"network access is blocked in sweep
mode"`); `from_dict` without `target`/`kind`/`level` → `ValueError` with `"missing key"`.

#### 3.5.3 `quartz/scan.py`

```python
TRACKED_ROOTS: frozenset[str] = frozenset({"bpy", "mathutils", "bmesh", "bpy_extras", "gpu", "gpu_extras", "blf",
                                           "idprop", "aud", "addon_utils", "bl_math", "rna_prop_ui"})
def symbol_depth(parts: Sequence[str]) -> int          # number of segments of the canonical symbol (table below)
@dataclass
class ScanResult:
    target: str; files: int; parse_errors: list[str]; symbols: "collections.Counter[str]"; bl_info: dict | None
    manifest_problems: list[str]; predicted: dict[str, list[str]]        # {"PHANTOM": [...], "MISSING": [...]}
    manifest: str | None = None    # addition: name of the manifest file found in the folder (BLENDER_MANIFEST/QUARTZ_MANIFEST) or None
    def to_dict(self) -> dict
        # all the field keys; symbols -> dict with sorted keys; bl_info: tuples -> lists, set/frozenset -> list
        # sorted by repr, any other non-JSON value (bytes, complex) -> repr(value); serializable by json.dumps without default=
def scan_source(source: str, *, filename: str = "<string>") -> "collections.Counter[str]"
def scan_path(path: str | Path, *, predict_missing: bool = True) -> ScanResult
def predict(symbols: Iterable[str], *, classify: Callable[[str], str] | None = None) -> dict[str, list[str]]
```

Own scanner, using only `ast` (MUST NOT import `tools/` or `tools.scan_bpy_usage`); the rules
reproduce those of the project's usage survey, so that the results are comparable with
`data/bpy_usage.json`.

**`scan_source(source, filename)`** (`ast.parse(source, filename)`; `SyntaxError` propagates):

1. **Name table** (flat, per file; walks the whole tree with `ast.walk`, including
   function bodies; on conflict the **last** binding in `ast.walk` order wins):
   `import X` / `import X.Y` with a root in `TRACKED_ROOTS` binds the first component (`"bpy"` →
   `"bpy"`); `import X.Y as A` binds `A` → `"X.Y"`; `from X.Y import N [as A]` (absolute, tracked
   root) binds `A`/`N` → `"X.Y.N"`; `from X import *` and relative imports are ignored.
2. **Namespace aliases**: collects the module-level statements as follows: initial stack = module body;
   repeatedly pops the **last** element of the stack, appends it to the list and, if it is
   `if`/`try`/`with`, pushes `body`, `orelse`, `finalbody` and the bodies of the `except` handlers (in that order).
   Walks the list in that order: each `ast.Assign` with a single `ast.Name` target not yet bound (by
   import or by an earlier alias in this same pass), whose value resolves (through the current table) to
   a chain rooted in `bpy, mathutils, bmesh, bpy_extras, gpu, blf, idprop, aud, gpu_extras,
   addon_utils` with fewer segments than `symbol_depth(chain)`, binds `NAME` → chain
   (`C = bpy.context`, `ops = bpy.ops`). Assignments inside functions or classes never create
   an alias.
3. **References**: each `ast.Name` in `Load` context and each `ast.Attribute` in any context
   (including `Store`/`Del`), both only when they are the top of a chain (they are not the `.value` of an
   `ast.Attribute`), whose dotted chain ends in an `ast.Name` present in the table, is resolved (`table base` +
   remaining segments); chains with fewer than 2 segments are ignored; the symbol is the prefix of
   `symbol_depth(parts)` segments; adds 1 to the `Counter`. A chain whose base is not an `ast.Name` (e.g.
   `f().x`, `a[0].x`) is not resolved, but the inner subexpression that is the top of a chain is (e.g.
   `bpy.data.objects["Cube"].location` counts `"bpy.data.objects"`).
4. `symbol_depth`: `bpy.ops.*` → 4; `bpy.utils.{previews,units,toolsystem}.*` → 4;
   `bpy.app.{handlers,translations,timers,icons,driver_namespace}.*` → 4;
   `bpy.{types,props,data,context,utils,app,path,msgbus}.*` → 3; any other `bpy.*` → 2;
   `mathutils.{geometry,kdtree,bvhtree,noise,interpolate}.*` → 3, any other `mathutils.*` → 2;
   `bmesh.{ops,types,utils,geometry}.*` → 3, any other `bmesh.*` → 2; `bpy_extras.*`, `gpu.*`,
   `gpu_extras.*`, `idprop.*` → 3; remaining roots → 2.

Normative examples: `bpy.ops.mesh.primitive_cube_add(size=2)` → `"bpy.ops.mesh.primitive_cube_add"`;
`bpy.context.scene.frame_current` → `"bpy.context.scene"`; `from bpy.app.handlers import persistent`
+ `@persistent` → `"bpy.app.handlers.persistent"`; `mathutils.Vector((1, 2, 3)).x` →
`"mathutils.Vector"`; `import bpy as b` + `b.types.Operator` → `"bpy.types.Operator"`.

**`scan_path(path, predict_missing)`**: nonexistent path → `FileNotFoundError`; file → only that file,
`target` = `stem`; folder → every `*.py` recursively whose path has no `__pycache__` component
(same set of files as the usage survey), sorted by POSIX relative path, `target` =
folder name. Each file is read as UTF-8; `UnicodeDecodeError` → re-read as latin-1 (same
rule as the survey); `SyntaxError` → `parse_errors` receives `f"{rel}:{lineno}: {msg}"` (`rel` =
POSIX path relative to the folder, or the file name) and the file contributes no symbols.
`files` = number of files read. `bl_info` = `quartz.addons.bl_info.read_bl_info(p)` with `p` = the
file, or the folder's `__init__.py` (missing → `None`). A folder with `blender_manifest.toml` or
`quartz_manifest.toml` (`quartz.addons.manifest.BLENDER_MANIFEST`/`QUARTZ_MANIFEST`; both → the
Blender one wins) → `manifest` = that name and `parse_manifest(folder, strict=False)` (same strictness as the
loader's discovery, §3.4.4); `ManifestError` → `manifest_problems = list(exc.problems)`; no
manifest or a valid one → `[]`. `predicted` = `predict(symbols)` if `predict_missing`, otherwise
`{"PHANTOM": [], "MISSING": []}`. `scan_path` requires `quartz.addons` (inside the function) and never
imports the scanned code.

**`predict(symbols, classify)`**: default `classify` = `quartz.compat.classify_symbol` (resolved at
call time; temporarily enables strict compat if needed and, for `bpy.ops`, uses
`quartz.session.current()`, §3.1.1). Each distinct symbol is classified once; `ValueError` from
`classify` (symbol outside the shims) → `"MISSING"`; `"IMPLEMENTED"` is omitted; always returns both
keys `"PHANTOM"` and `"MISSING"` with sorted lists. `classify` omitted and `quartz.compat`
unavailable (rule 2) → both lists empty, no error.

#### 3.5.4 Goldens: `tools/golden_runner.py`, `tools/run_golden.py`, `tests/golden/**`, `data/golden/**`

The same golden script runs in Blender and in Quartz, through the same runner (ARCHITECTURE §11, item 5; D18);
the Blender results are versioned in `data/golden/<script>.blender.json`.

Files in `tests/golden/`: `harness.py` (library, not a test), `scripts/g01_factory_scene.py`
… `scripts/g13_mathutils_numeric.py` (list below) and `test_golden.py`. `harness.py` and the scripts
also run inside Blender: stdlib + `bpy`/`mathutils` only; they MUST NOT import `quartz` or
numpy.

```python
# tests/golden/harness.py — loaded by path under the module name "qz_golden_harness"
FORMAT: str = "quartz.golden"; FORMAT_VERSION: int = 1; DEFAULT_TOL: float = 1e-5
def reset() -> None                                   # empties results, options and meta
def set_meta(**meta: object) -> None                  # script, host, host_version
def normalize(value: object) -> object
def emit(key: str, value: object, *, tol: float | None = None, unordered: bool = False) -> None
    # repeated key -> ValueError("duplicate golden key: ...")
def capture(key: str, fn: Callable[[], object], *, fragments: Sequence[str] = (), tol: float | None = None,
            unordered: bool = False) -> object
    # success: emit(key, {"ok": normalize(ret)}) and returns ret; exception e: emit(key, {"exc": <builtin>, "msg": str(e),
    # "fragments": list(fragments)}) and returns None; <builtin> = __name__ of the 1st class in the MRO of type(e) with __module__ == "builtins"
def document() -> dict      # {"format", "format_version", "script", "host", "host_version", "results": {...}, "options": {key: {"tol", "unordered"}}}
def compare(expected: Mapping, actual: Mapping, *, divergences: Mapping[str, str] | None = None) -> list[str]
```

`normalize` (rules tested in this order, recursive): `None`/`bool`/`int`/`str` unchanged;
`float` unchanged, non-finite → `{"__float__": "nan"|"inf"|"-inf"}`; object whose class is named
`Vector`, `Euler`, `Quaternion` or `Color` → list of `float`; `Matrix` → list of rows (lists of
`float`); `set`/`frozenset` → list of the normalized items sorted by `json.dumps(item,
sort_keys=True)`; `tuple`/`list` → list; `dict` with all `str` keys → `dict`; object with
`bl_rna` → `{"__rna__": bl_rna.identifier}` + `"name": obj.name` if it has `name`; any other object with
`__len__` and `__getitem__` that is not `bytes`/`dict` (e.g. Blender's `bpy_prop_array`, such as
`World.color`, and `quartz.rna.PropArray`) → list of normalized `obj[i]`; anything else → `TypeError` with
`"cannot normalize"`.

`emit` stores `normalize(value)` in `results[key]` and, if `tol is not None` or `unordered`,
`options[key] = {"tol": tol, "unordered": unordered}` (a key without options does not appear in `options`).

`compare(expected, actual)`: for each key of `expected["results"]` (sorted) that is not
`f"{script}.{key}"` in `divergences`: missing from `actual` → `f"{key}: missing"`; values
compared recursively with a path (`key[2].x`): `bool` only with an equal `bool`; numbers with
`abs(a - b) <= tol` (`tol` from the options of `expected`, otherwise `DEFAULT_TOL`; `int` × `int` exact);
lists with the same length, element by element, or, if the key has `unordered`, both lists
sorted by `json.dumps(item, sort_keys=True)` and then compared element by element (only at the top
level of the key's value); dicts with the same keys; `{"__float__": ...}` equal only to itself;
`str`/`None` by equality; exception: `exc` equal and each fragment of `expected` contained
in `actual["msg"]` (the whole message is never compared); `{"ok": ...}` × `{"exc": ...}` is
a difference. Extra keys in `actual` are ignored. Returns the messages in order.

**Golden scripts** (original code; each one starts from the factory scene that the host already provides —
`--factory-startup` in Blender, `reset("default")` of `run-script`, `bpy_lenient` fixture in the test —
and does not recreate it; does not write files; uses `import qz_golden_harness as h`; values that depend on
`float32` are emitted as read, with the default `tol`). Required minimum keys (the script's author MAY emit more):

| Script | Emits (key prefixes) | Pins down |
|---|---|---|
| `g01_factory_scene` | `objects.names`, `collection.objects`, `camera.*` (location, rotation_euler, lens, sensor_width, clip_start, clip_end, type), `light.*` (type, energy, shadow_soft_size, color, location), `world.color`, `scene.*` (frame_start/end/current, fps, resolution_x/y/percentage, engine), `cube.counts` (verts/edges/polys/loops), `cube.co` (`unordered`), `materials.users`, `view_layer.name`, `active`, `selected`, `wm.name`, `screen.name`, `workspace.name` | factory scene from §2.6.1 **[O]** |
| `g02_id_naming` | `.NNN` suffixes on collision, rename that carries the suffix, 300-byte name with accents (truncation), empty name, `rename` in the three modes and result, iteration order of `_x, a, A, a10, a2, b, B, Zed` | §2.1.4(5) |
| `g03_users_and_remove` | `users` of mesh/material/world/scene camera/parent; `meshes.remove` cascading; `objects.remove` leaving a mesh with 0 users; access to a removed one (`capture`, fragment `"has been removed"`); `orphans_purge` | §2.1.4 |
| `g04_mesh_from_pydata` | counts for a quad and for two triangles, `edge_keys` (`unordered`), `validate()`, face normals and areas, `loop_start/loop_total`, `foreach_get("co")` | §2.3.1 |
| `g05_primitives` | for each default `mesh.primitive_*_add` (without `monkey`): counts and bounding box (min/max) — never the vertex order (divergence 6, ARCHITECTURE §13) | counts **[O]** |
| `g06_object_transforms` | the 8 rotation modes, deltas, parent with and without `matrix_parent_inverse`, writing `matrix_world` → `location`, negative scale (`decompose`); `matrix_world` is only read after `view_layer.update()` (D9) | §2.2.6 **[I]** |
| `g07_props_semantics` | `PropertyGroup` on `Scene`: clamp, accepted/rejected coercions (`capture`), integer enum `get/set`, `ENUM_FLAG`, `maxlen` in bytes, float32 reading, number of `update` calls | §1.6.4 |
| `g08_registration_errors` | registration without `bl_label`, invalid `bl_idname` (the three reasons), double registration, `unregister` without registration, invalid class enum (`capture` with the fragments from §2.1.6) | §2.1.6 **[O]** |
| `g09_operator_contract` | invalid positionals, false `poll` with and without `poll_message_set`, invalid returns, `report({"ERROR"})`, `INVOKE_DEFAULT` → `execute`, values that do not persist | §2.1.8 |
| `g10_context_override` | `temp_override` (known and unknown members), keys of `copy()` (fixed subset), `path_resolve`, writing to a member (`capture`, `"is read-only"`) | §2.6.2 |
| `g11_collections_linking` | link/unlink, duplicate link (`"already in collection"`), cycle, order of `children`, view layer objects, `users_collection` | §2.2.7 |
| `g12_handlers_frame_set` | order of `frame_change_pre/post` with `frame_current` as seen in `pre`, number of `depsgraph_update_post` after changing a prop and calling `view_layer.update()`, `persistent` | §2.1.2 **[O]** |
| `g13_mathutils_numeric` | with `random.Random(1234)`: inverse, `decompose`, Euler ↔ Quaternion in the 6 orders, `slerp`, `to_track_quat`, `repr`/`str` | §1.4 |

**`tools/golden_runner.py`** (runs inside the host; does not import `quartz`): reads from `sys.argv` what comes
after `"--"`: `SCRIPT OUT`. Loads `tests/golden/harness.py` by path (relative to the file itself),
registers it in `sys.modules["qz_golden_harness"]`, `reset()`, `set_meta(script=<stem>,
host="quartz" if "quartz" in sys.modules else "blender", host_version=sys.modules["quartz"].__version__
if "quartz" in sys.modules, else bpy.app.version_string)` (the runner reads the version from `sys.modules`,
without importing `quartz`), `runpy.run_path(SCRIPT, run_name="__main__")` and writes `document()` to
`OUT` (`sort_keys=True`, `indent=1`, `ensure_ascii=False`, trailing `"\n"`, UTF-8; creates the folder). Script
failure: traceback on `stderr`, `OUT` is not written and the exception is re-raised (in Blender
`--python-exit-code 1` becomes code `1` **[I]**; in Quartz, `exec_script` gives `1`). Wrong arguments
or `OUT` outside the project root (`Path(__file__).resolve().parents[1]`) → `SystemExit(2)` (which Quartz's
`run-script` delivers as `1`, §3.5.2). The caller treats every code ≠ 0 as a failure.

**`tools/run_golden.py`** (runs in the `.venv`; inserts `Path(__file__).resolve().parents[1]` into
`sys.path` and loads `tests/golden/harness.py` by path to use `compare`):
`python tools/run_golden.py [--host blender|quartz|both] [--only NAME]... [--update]
[--blender-exe PATH] [--timeout S] [--out-dir DIR]` (defaults: `both`, all the scripts in
`tests/golden/scripts/` by name, exe = env `QUARTZ_BLENDER_EXE` or
`C:/Program Files/Blender Foundation/Blender 5.2/blender.exe` (the `BLENDER_EXE` rule from §1.1.2,
reimplemented), `120` s, `<root>/tmp/golden`). `--out-dir` outside the root → `2` with `"outside the project
root"`; `--only` with an unknown name → `2`. All paths passed to the hosts are absolute.

- Blender: `[exe, "--background", "--factory-startup", "--python-exit-code", "1", "--python",
  "<root>/tools/golden_runner.py", "--", script, output]`, with `BLENDER_USER_RESOURCES`,
  `BLENDER_USER_CONFIG`, `BLENDER_USER_SCRIPTS`, `BLENDER_USER_EXTENSIONS`, `BLENDER_USER_DATAFILES`
  under `<root>/tmp/blender_user` (same layout as `tools/run_dump_bpy_api.ps1`), `cwd =
  <out-dir>/cwd`; output in `<out-dir>/<name>.blender.json`; it is copied to
  `data/golden/<name>.blender.json` **only** with `--update`.
- Quartz: `[sys.executable, "-B", "-X", "utf8", "-m", "quartz", "run-script",
  "<root>/tools/golden_runner.py", "--", script, output]` with `cwd = <root>` (so that `-m quartz`
  finds the package), `QUARTZ_USER_DIR = <out-dir>/user`; output in `<out-dir>/<name>.quartz.json`.
- Comparison per script: `--host both` → `compare(blender, quartz)`; `--host quartz` →
  `compare(<versioned>, quartz)` (no versioned file: warning `"Blender golden missing"`, script
  skipped, does not change the exit code); `--host blender` → `compare(<versioned>, blender)` if the versioned file
  exists and `--update` was not given. Prints the differences in English; code `1` if there is a difference or
  a process failure, `2` if the requested Blender does not exist (`"Blender not found"`), `0` otherwise.
  Timeout → failure of that script.

**`data/golden/**`**: one `<script>.blender.json` per script in `tests/golden/scripts/`, generated with
`tools/run_golden.py --host blender --update` on Blender 5.2.2 (installed on this machine) and
versioned; `host == "blender"`, `host_version == "5.2.2 LTS"`. Never edited by hand.

#### 3.5.5 Baseline and ratchet: `tools/blender_sweep_baseline.py`, `tools/run_blender_baseline.py`, `data/sweep/**`

**`tools/blender_sweep_baseline.py`** (runs inside Blender; does not import `quartz`; first useful
statement: `sys.dont_write_bytecode = True`). Arguments after `"--"`: `--scripts DIR --out FILE`
and `--addons [--only NAME]...` or `--template PATH`.

- Counted bases (`REGISTRABLE_BASES`): the 18 keys of `base_classes` in the dump except `bpy_struct`
  **[O]** (`Operator`, `Macro`,
  `Panel`, `Menu`, `Header`, `PropertyGroup`, `AddonPreferences`, `UIList`, `KeyingSetInfo`,
  `RenderEngine`, `Node`, `NodeSocket`, `NodeTree`, `Gizmo`, `GizmoGroup`, `WorkSpaceTool`,
  `FileHandler`, `AssetShelf`) + `NodeTreeInterfaceSocket` (inert base from §2.5.5): 19 bases.
  `HydraRenderEngine` is NOT a counted base: its subclasses count under `RenderEngine`, as in
  `registry.registrable_base_of` (§2.5.5, rule 3). Registered classes = subclasses (recursive, via `__subclasses__`) of `bpy.types.<base>`
  with `is_registered` true **[I]**; each class counts under the most derived base in the list present
  in its MRO (same criterion as `registry.registrable_base_of`/`counts_by_base`, §2.5.1).
- `--addons`: one session for all the add-ons in `DIR/addons_core` (same listing as
  `discover_blender_targets`, reimplemented with stdlib only), in order; per add-on: `STATIC` (all
  `.py` files parse with `ast`); `METADATA` (`bl_info` readable without importing, same rule as
  §3.4.2); `addon_utils.enable(name, default_set=True, handle_error=<records>)` (same `default_set`
  as `enable_with_report`, §3.4.5) → returned module =
  `REGISTER`; a failure whose traceback has a frame named `register` inside the add-on folder =
  `IMPORT`, any other failure = `METADATA` **[I]**; `UI_SMOKE` is not measurable headless and counts as
  achieved when `REGISTER` was **[I]**; `addon_utils.disable(name, default_set=True,
  handle_error=<records>)` with no error and no leak in the categories measurable with `bpy` =
  `UNREGISTER_CLEAN` **[I]**: (a) classes: no class registered by `enable` is still registered;
  (b) handlers: no entry in any list of `bpy.app.handlers` whose `__module__` is the
  add-on or starts with `name + "."`, present after `disable` and absent before `enable`; (c)
  dynamic props: for each struct in `bpy.types` with `bl_rna`, `bl_rna.properties.keys()` after
  `disable` equal to the one from before `enable`. Leaks of menu functions are not measurable in
  Blender (there is no owner per function) and are not measured; `compare_baseline` (§3.5.2) compensates for this.
  `registered` = new classes after `enable`, per base.
- `--template PATH`: one template per process; `STATIC`, `METADATA` vacuously; before running,
  `sys.argv = [PATH]` (without the `"--"` and this tool's arguments, exactly like Quartz's
  `exec_script` without `ARGS`; restored afterwards), because templates such as `background_job.py`
  read what comes after `"--"`; `runpy.run_path(PATH, run_name="__main__")` with no exception
  (`SystemExit` 0/`None` accepted) = `IMPORT`; `registered` = class delta per base.
- Writes `{"format": "quartz.sweep.baseline.part", "blender_version": list(bpy.app.version),
  "targets": {name: {"kind", "level", "registered", "error", "seconds"}}}`.

**`tools/run_blender_baseline.py`** (runs in the `.venv`; inserts `Path(__file__).resolve().parents[1]`
into `sys.path` and imports `quartz.sweep`): `python tools/run_blender_baseline.py [--blender-exe PATH]
[--scripts DIR] [--out FILE] [--only NAME]... [--timeout-addons S] [--timeout-template S]` (defaults:
the `BLENDER_EXE` rule from §1.1.2, `quartz.sweep.DEFAULT_BLENDER_SCRIPTS`,
`data/sweep/blender_baseline.json`, `600`, `20`). Runs Blender (same command line and same redirected
user environment as `run_golden.py`, `cwd = <root>/tmp/sweep/blender_cwd`) once
with `--addons` (all add-ons, or those from `--only`) and once per template (filtered by `--only`);
parts in `tmp/sweep/blender/addons.json` and `tmp/sweep/blender/<safe>.json` (`safe` as in
`run_target`); timeout or missing part → entry `{"kind": ..., "level": "NONE", "registered": {},
"error": "timeout after S s" | "no output", "seconds": ...}` for each affected target; merges everything into
`{"format": "quartz.sweep.baseline", "format_version": 1, "blender_version": <from the part, [5, 2, 2]
**[O]**>, "targets": {...}}` (targets sorted by name; JSON as in rule 4 of the task) and writes to
`--out` (outside the root → `2`). Target names and kinds = those of
`quartz.sweep.discover_blender_targets`. Codes: `0`; `1` if any process failed; `2` without
Blender or with an invalid argument.

**`data/sweep/**`**:

| File | Contents | Written by |
|---|---|---|
| `blender_baseline.json` | format above; 13 add-ons + 38 templates **[O]** | `tools/run_blender_baseline.py` (generated during implementation and versioned) |
| `ratchet.json` | `{target: level}`; MUST exist (at minimum `{}`) | `addon-sweep --update-ratchet` (only goes up) |
| `quartz_latest.json`, `quartz_latest.md` | `to_json`/`to_markdown` of the corpus sweep | `python -m quartz addon-sweep --json data/sweep/quartz_latest.json --md data/sweep/quartz_latest.md` (command documented in the README; MAY be versioned) |

Tests do NOT write to `data/sweep/` (§0.1(5)); they use `tmp_path`. Item 7 of the gate (§3.0.8) is
fulfilled by the command in the `quartz_latest.*` row above (outside pytest), followed by
`test_corpus_sweep.py`, which verifies the ratchet.

#### 3.5.6 `tests/fixtures/scripts/**`

Exactly four scripts, each with the header from §0.1(1), original code, made to run
with compat active (those that use the API do `import bpy`), without writing to disk or using the network, and
printing only to `stdout`:

| File | Does | Expected result (`run_target_inprocess` / subprocess) |
|---|---|---|
| `qz_script_ok.py` | defines and registers `Operator` `qz.script_ok` (`bl_label` "QZ Script OK"), calls `bpy.ops.qz.script_ok()`, prints `qz_script_ok: FINISHED`; does not unregister (like the templates) | `IMPORT`, `ok`, `registered == {"Operator": 1}` |
| `qz_script_raises.py` | `raise RuntimeError("qz_script_raises: intentional failure")` at module level | `METADATA`, `error_type "RuntimeError"`, `error` contains `"intentional failure"`; `run-script` → code `1` |
| `qz_script_argv.py` | prints `json.dumps(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])` | `IMPORT`; `run-script FILE -- a b` prints `["a", "b"]` |
| `qz_script_ops.py` | calls `bpy.ops.mesh.primitive_cube_add()` and prints `json.dumps({"objects": len(bpy.data.objects), "meshes": len(bpy.data.meshes)})` | `IMPORT`; in the factory scene it prints `{"objects": 4, "meshes": 2}`; with `--empty`, `{"objects": 1, "meshes": 1}` |

#### 3.5.7 `README.md` and `docs/ROADMAP.md`

Human documents in English (§0.1(2)), with no text copied from Blender or Cinema 4D.

`README.md` MUST contain, in this order: title `# Quartz`; what it is (headless 3D core, a fusion of
ideas from Cinema 4D with the `bpy` API; Path C and Path A) and authorship **D1on1n**; requirements (Python
≥ 3.13, numpy; runs from the root, no installation); how to run the tests
(`.venv/Scripts/python.exe -m pytest -q` and the variables `QUARTZ_RUN_BLENDER`, `QUARTZ_RUN_SWEEP`,
`QUARTZ_BLENDER_EXE`, `QUARTZ_BLENDER_SCRIPTS`); the CLI with one example of each of the five
subcommands and the table of exit codes; the layers (L1/L2/L3) with a link to
`docs/ARCHITECTURE.md` and `docs/CONTRACTS.md`; compat (`quartz.compat.activate`, strict × lenient,
link to `docs/COMPAT.md`); sweep, baseline, ratchet and goldens (how to regenerate with
`tools/run_blender_baseline.py` and `tools/run_golden.py --update`); clean-room note.

`docs/ROADMAP.md` MUST contain: the "deferred" table from ARCHITECTURE §15 (item, state at the milestone, how it
comes in later), rewritten; the milestone's sweep goals (fixtures 100 % at the expected level; templates
matching the baseline in at least 30 of 38; out-of-scope add-ons `cycles` and `bl_pkg`) marked
as goals, not measurements; the rule "the backlog comes from `missing_symbol_ranking`" with a link to
`data/sweep/quartz_latest.md`; the open decisions from ARCHITECTURE §16; the future level `SCENARIO`.

#### 3.5.8 Tests

Isolation before the sibling modules (§0.6): `test_levels.py`, `test_baseline_ratchet.py`, the
`scan_source`/`symbol_depth`/`predict(classify=<false>)` parts of `test_scan.py` and the usage parts of
`test_cli_main.py` (steps 1–2 of `main`, `build_parser`, `--help`/`--version`) depend only on L1/L2
and pass without `quartz.compat`/`quartz.addons`/`quartz.extras`/`quartz.bmesh`; the rest (including
`scan_path`, which reads `bl_info`/manifest via `quartz.addons`) passes at the L3 gate. Tests that call
`main` with a subcommand that reaches step 6, or that touch the session, use `qz`/`qz_empty`/`bpy`/
`bpy_lenient` (§1.1.2); tests that enable Blender add-ons use `bpy`/`bpy_lenient` (§3.0.4).
`tests/cli/conftest.py` and `tests/sweep/conftest.py` define, identically, the fixture
`addon_sandbox` (function scope; uses `qz_user_dir`; in tests it is requested **after** `qz`/`bpy_lenient`, so that
it is torn down before them): it saves the keys of `sys.modules`, a copy of `sys.path` and
`sys.dont_write_bytecode`; sets `sys.dont_write_bytecode = True`; on exit it calls
`quartz.addons.MANAGER.q_reset()` (if available), removes from `sys.modules` the new keys whose
first component is `bl_ext` or `qz_ext` or that start with `qz_fx_`/`qz_script_`/`qz_t_`, restores
`sys.path[:]` and the flag. Subprocess tests use `work_dir=tmp_path` (or `--work-dir <tmp_path>`) and
marker `slow`. Add-ons/scripts created by the tests themselves in `tmp_path` use names `qz_t_*` and the
header from §0.1(1).

- `tests/cli/conftest.py`, `tests/sweep/conftest.py`: only the `addon_sandbox` fixture above.
- `tests/cli/test_cli_main.py`: `build_parser()` has exactly the five subcommands and the options from
  §3.5.1; `main(["--help"])` → `0`; `main(["--version"])` → `0` and `"quartz 0.1.0"` in `stdout`;
  `main([])`, `main(["bogus"])`, `main(["addon-sweep", "--jobs", "0"])`, `main(["addon-sweep",
  "--timeout", "0"])` and `main(["run-script", "<tmp_path>/nothing.py"])` → `2`, without creating a session
  (verified with `monkeypatch` on `quartz.session.current` that fails); splitting of `ARGS`
  (`["run-script", "x.py", "--", "--json"]` → `args.script_args == ["--json"]` and `args.json` false);
  under `qz`, `main(["info"])` dispatches `startup_post`, `shutdown_pre`, `shutdown_post` in that order
  (test functions appended to the lists of `quartz.app.handlers`; `info` does not reset the session);
  `cmd_info` replaced (monkeypatch) by a function that raises → `3`, `"internal error"` in `stderr`, and
  `shutdown_pre`/`shutdown_post` still dispatched; `quartz.app.settings.snapshot()` equal before and
  after `main(["enable-addon", <qz_fx_single.py>, "--no-restrict", "--json"])` (gate;
  `bpy_lenient` + `addon_sandbox`); `sys.dont_write_bytecode` restored; `README.md` and
  `docs/ROADMAP.md` exist, the README starts with `# Quartz`, contains the five subcommands and
  `"D1on1n"`, the ROADMAP contains `"SCENARIO"`.
- `tests/cli/test_cli_info.py` (under `qz`): `info --json` is JSON with exactly the top-level keys from
  §3.5.1 (`quartz`, `python`, `numpy`, `platform`, `paths`, `compat`, `registry`, `session`,
  `handlers`), `quartz.version == "0.1.0"`, `quartz.author == "D1on1n"`, `session.objects == 3`,
  `session.template == "default"`, `handlers == {"blender": 39, "quartz": 5}`,
  `registry.builtin_operators` ≥ 43 (the operators in the §2.7 table), `compat.active is False`;
  `quartz.compat.is_active()` false after the command; text contains `"Quartz 0.1.0 (author: D1on1n)"`
  and `"Session:"`.
- `tests/cli/test_cli_scan.py` (under `qz`): `scan-addon` on `tests/fixtures/addons/qz_fx_single.py`
  → `0`, JSON with non-null `bl_info` and `"bpy.types.Operator"` in `symbols`; on
  `qz_fx_no_bl_info.py` → `1`; on `extensions/qz_fx_repo/qz_fx_ext` → `0` and `manifest ==
  "blender_manifest.toml"`; on `extensions/qz_fx_repo/qz_fx_bad_manifest` → `1` and
  `manifest_problems` non-empty; on `<tmp_path>/qz_t_broken.py` containing only `def broken(:` → `1`
  and `parse_errors[0]` contains `":1:"`; nonexistent path → `2` with `"not found"`; the command does not
  import the scanned module (`"qz_fx_single"` absent from `sys.modules` afterwards).
- `tests/cli/test_cli_enable_addon.py` (`bpy_lenient` + `addon_sandbox`): `enable-addon <path of
  qz_fx_single.py> --smoke-ui --json` → `0`, `level == "UNREGISTER_CLEAN"`, `registered ==
  {"Operator": 1, "Panel": 1}`, `ui_smoke["failed"] == 0`; `qz_fx_register_fails.py` → `1`, `level
  == "IMPORT"`; `qz_fx_single.py --keep-enabled --json` → `0`, `level == "UI_SMOKE"`, `ok`, and
  `MANAGER.check("qz_fx_single")[1] is True` afterwards; `enable-addon qz_fx_single --path
  <fixtures/addons> --json` (by name) → `0`; nonexistent name → `2` with `"add-on not found"`;
  `--repo noequals` → `2` with `"invalid --repo"`; `<tmp_path>/qz_t_printer.py` (with `bl_info`, whose
  `register` prints to `stdout`) with `--json` → `stdout` is a single JSON object (`json.loads` of the
  entire captured `stdout`); `<tmp_path>/qz_t_net.py` whose `register` calls
  `socket.create_connection(("127.0.0.1", 9))`, with `--sweep-mode --json` → `error_type ==
  "PermissionError"` and `"network access is blocked in sweep mode"` in `error`, and after `main`
  `socket.create_connection` and `socket.socket.connect` are the originals again.
- `tests/cli/test_cli_run_script.py` (`qz` + `addon_sandbox`): the four scripts from §3.5.6 with the
  codes and outputs from the table (`capsys`); `-- a b` arrives as `["a", "b"]`; `--empty` changes the
  counts of `qz_script_ops`; `--no-compat` with `qz_script_ok` → `1` (`"ModuleNotFoundError"` and
  `bpy` in `stderr`); `--json` with `qz_script_raises` → `1`, JSON with `level == "METADATA"` and
  `error_type == "RuntimeError"`; `--json` with `qz_script_ok` → `0`, `registered == {"Operator": 1}`;
  nonexistent file → `2`; after each command `quartz.compat.is_active()` is false and `sys.argv` is the one from
  before; `--addon qz_fx_single` (with `quartz.app.paths.add_addon_dir(<fixtures/addons>)` beforehand)
  enables the add-on before running the script (`MANAGER.check("qz_fx_single")[1] is True`); `--addon
  qz_t_nothing` → `1` with `"add-on not enabled"` and the script does not run.
- `tests/cli/test_cli_addon_sweep.py` (`qz`, `slow`): `addon-sweep --fixtures --work-dir <tmp>
  --json <tmp>/r.json --md <tmp>/r.md --ratchet <tmp>/ratchet.json --update-ratchet` → `0`; the JSON
  has `format == "quartz.sweep"` and one result per target (11 add-ons/extensions + 4 scripts) with the
  expected level (§3.4.8, §3.5.6); the Markdown contains `"# Quartz sweep report"`; the written
  ratchet has the 15 targets; repeating with the ratchet tampered upward (`"qz_fx_leaky":
  "UNREGISTER_CLEAN"`) → `1` and `"regression at the ratchet"` in `stdout`; `--fixtures --only
  qz_fx_single` → one result; `--fixtures --only nothing` → `2` with `"unknown target in --only"`;
  `--json C:/qz_out.json` (outside the root, which is on `D:`) → `2` with `"outside the project root"`;
  `--blender-scripts <tmp>/nonexistent` → `2` with `"Blender scripts directory not
  found"`; `--blender-scripts <tmp empty> --no-templates` → `1` with `"no target"`.
- `tests/sweep/test_levels.py` (no L3 siblings): exact `LEVELS` and `TARGET_KINDS`; `level_index` and
  `ValueError` (`"unknown sweep level"`); `max_level` in the three cases; `module_name_for` for the five
  kinds (`SCRIPT` → `ValueError` with `"script targets have no module name"`);
  `SweepResult.to_dict()` serializable by `json.dumps` and `from_dict(to_dict())` equal; `from_dict`
  without `level` → `ValueError` (`"missing key"`); `missing_symbol_ranking` (descending count,
  then symbol; sorted targets); deterministic `to_markdown` (same input with equal `seconds`
  → same text) and with the titles from §3.5.2 in order; `to_json()["levels"]` has the 7 keys;
  `boot_command(["info"])[1:6] == ["-I", "-B", "-X", "utf8", "-c"]` and `BOOT` contains
  `repr(str(PROJECT_ROOT))` and `"quartz.cli"`; `network_guard` (`connect`, `connect_ex` and
  `create_connection` blocked; nested; restoration after an exception; message); `target_from_path`
  with trees in `tmp_path` (file, `__init__.py`, package, extension, native, empty folder →
  `ValueError` with `"not an add-on"`; relative path → absolute `path`);
  `discover_blender_targets` on a fake tree in `tmp_path` (order, names `templates_py/...`,
  `modules` ignored, invariant `target_from_path(t.path) == t` for the add-ons) and missing root →
  `FileNotFoundError` (`"Blender scripts directory not found"`); `exec_script` with scripts in
  `tmp_path` (`__name__ == "__main__"`, `sys.argv` with and without `ARGS` and restored afterwards,
  `SystemExit(0)` → `0`, `SystemExit(3)` → `1`, exception → `error_type` and `traceback`);
  `ui_smoke` under `qz` with fake classes registered under `registry.owner_scope("qz_t_owner")` (one
  drawable `Panel`, one with a false `poll`, one whose `draw` raises, one whose `poll` raises and a
  simple `UIList`) → `{"drawn": 2, "failed": 2, "skipped_poll": 1}`.
- `tests/sweep/test_fixture_sweep.py` (gate §3.0.8(3)): `discover_fixture_targets()` returns the
  names and kinds from the §3.4.8 table + the 4 scripts, in the order of §3.5.2, with the invariant of
  `target_from_path`; in-process (`bpy_lenient` + `addon_sandbox`, `run_target_inprocess(t,
  smoke_ui=True)`, one target per parametrized test, except the native one) each target reaches the
  expected level (§3.4.8; scripts: §3.5.6) and `ok` only for those that reach the maximum; details:
  `qz_fx_single` `ui_smoke["drawn"] >= 1` and `failed == 0`; `qz_fx_menu.menus_extended` contains
  `TOPBAR_MT_file_import` and `VIEW3D_MT_object`; `qz_fx_leaky.leaks` non-empty; `qz_fx_restricted`
  has `error_type == "RestrictedAccessError"`; `qz_fx_bad_manifest` mentions `paths` in `error` or
  `warnings`; the native one runs under `qz` (without `bpy`), reaches `UNREGISTER_CLEAN` and compat remains
  inactive; by subprocess (`slow`, `run_target(t, timeout=120, work_dir=tmp_path)`) the same
  levels, and `tmp_path/"user"/<safe>` exists for each target; `sweep(targets, jobs=2,
  work_dir=tmp_path)` preserves the input order.
- `tests/sweep/test_baseline_ratchet.py` (no L3 siblings): `compare_baseline` with a synthetic
  baseline covering `green`, `behind`, `ahead`, `count_mismatch` (zeros ignored), a
  `UI_SMOKE` result with only `"menu …"` leaks against an `UNREGISTER_CLEAN` baseline → `green` (and with a
  `"handler …"` leak → `behind`),
  `missing_in_baseline` and `summary`; `{}` → everything in `missing_in_baseline`; `check_ratchet` (only common
  targets, message `"a: UNREGISTER_CLEAN -> IMPORT"`); `update_ratchet` in `tmp_path` only goes up and
  writes sorted keys; `load_*` with a missing file → `{}`, wrong format → `ValueError`
  (`"not a sweep baseline"`, `"not a sweep ratchet"`, `"unknown sweep level"`);
  `data/sweep/ratchet.json` exists and `load_ratchet()` accepts it; `data/sweep/blender_baseline.json`,
  if it exists, has `format == "quartz.sweep.baseline"`, `blender_version == [5, 2, 2]`, 51 targets (13
  add-ons + 38 templates **[O]**) with levels in `LEVELS` and `registered` bases contained in the 19 from
  §3.5.5 (absent → `pytest.skip`).
- `tests/sweep/test_scan.py`: the normative examples from §3.5.3; `import bpy as b`; `from bpy.types
  import Operator as Op` + `class X(Op)` → `"bpy.types.Operator"`; module alias
  `C = bpy.context` followed (`C.scene` → `"bpy.context.scene"`), also inside module-level `if`/`try`;
  alias inside a function NOT followed; import inside a function counts; assignment
  `bpy.types.Scene.x = 1` counts `"bpy.types.Scene"`; `bpy.utils.previews.new()` → depth 4;
  `mathutils.geometry.intersect_line_line` → 3; `bmesh.ops.create_cube` → 3; `bl_math.clamp` → 2;
  `os.path.join` and relative/star imports ignored; repetition count; `SyntaxError`
  propagates in `scan_source`; `predict(..., classify=<false>)` omits `IMPLEMENTED`, sorts and treats
  `ValueError` as `MISSING`; `quartz/scan.py` does not import `tools` (verified by `ast`); gate:
  `scan_path` on a folder in `tmp_path` with a broken file (`parse_errors` with relative path
  and line; the other files contribute), `ScanResult.to_dict()` serializable; real `predict` (under
  `qz`): `"bpy.types.Operator"` does not appear in any list and `"bpy.data.actions"` is in
  `PHANTOM`; with marker `corpus` (fixtures `blender_scripts` and `blender_usage`): for each target of
  `discover_blender_targets` (13 add-ons and 38 templates), `scan_path(t.path,
  predict_missing=False)` has no `parse_errors` **[O]** (`population.parse_errors == 0`) and the
  set of symbols restricted to the roots `bpy, mathutils, bmesh, bpy_extras, gpu, blf, idprop,
  aud, gpu_extras, addon_utils` equals the set of keys of `symbols` of the homonymous group in
  `groups` of `data/bpy_usage.json`.
- `tests/sweep/test_corpus_sweep.py` (markers `sweep` and `slow`; fixture `blender_scripts`):
  `discover_blender_targets` finds 13 add-ons and 38 templates **[O]**; `sweep(..., jobs=min(4,
  os.cpu_count() or 1), timeout=60, work_dir=tmp_path)` returns a valid result per target (level
  in `LEVELS`, serializable `to_dict`); `check_ratchet(load_ratchet())` empty (the ratchet does not regress,
  §3.0.8(7)); writes `to_json`/`to_markdown` in `tmp_path` (never in `data/`).
- `tests/golden/test_golden.py`: `harness` loaded by path; `normalize` (fake classes
  named `Vector`/`Matrix`, sets, non-finite values, generic sequence, `TypeError` with `"cannot
  normalize"`), duplicate `emit` (`ValueError` with `"duplicate golden key"`), `options` only for
  keys with `tol`/`unordered`, `capture` (the name of the builtin in the MRO of
  `quartz.errors.PropertyTypeError` is `"TypeError"`) and `compare` (tolerance, `unordered`,
  fragments, `ok` × `exc`, missing key, omitted divergence) — without a session; for each
  `tests/golden/scripts/g*.py`, parametrized: without `data/golden/<name>.blender.json` →
  `pytest.skip("Blender golden missing: run tools/run_golden.py --host blender --update")`; with
  it, runs the script in-process under `bpy_lenient` (after `quartz.extras.install_adapters()` and
  `quartz.bmesh.install_adapters()`; harness in `sys.modules["qz_golden_harness"]` with `reset()` and
  `set_meta(script=<name>, host="quartz", host_version=quartz.__version__)`, removed afterwards;
  `runpy.run_path(script, run_name="__main__")`) and requires `compare(expected, harness.document(),
  divergences=DIVERGENCES) == []`; each `data/golden/*.json` has `format == "quartz.golden"`, `host ==
  "blender"`, `host_version == "5.2.2 LTS"` and a corresponding script; `DIVERGENCES: dict[str, str]`
  at module level (key `"<script>.<key>"`, non-empty English reason); with marker `blender`:
  `tools/run_golden.py --host blender --only g01_factory_scene --out-dir <tmp_path>` (subprocess)
  → `0` and `compare(<versioned>, <tmp_path>/g01_factory_scene.blender.json) == []`.

---

## Appendix A — Blender 5.2.2 Tables

Normative tables cited by §1.2.2, §1.2.5, §1.6.1 and §2.1.2, extracted from `data/blender_api_dump.json`
and `data/blender_facts_judge.json` (facts observed in Blender 5.2.2 **[O]**). Only names and values; no
Blender description is reproduced. Sections A.2 and A.3 do not exist (numbering reserved).

### A.1 Handler names

`quartz.app.handlers.BLENDER_HANDLER_NAMES` (§1.2.2) = these 39 names, in this order (dump `app.handler_lists`,
equal to the `list`-type keys of `app.handlers`) **[O]**. `QUARTZ_HANDLER_NAMES` (the 5 from §1.2.2) comes after
in `all_lists()`; the 44 lists are the only ones accepted by `dispatch`. Every name that §2.1.2 dispatches is here
(`frame_change_*`, `depsgraph_update_*`, `load_pre`, `load_post`, `load_post_fail`,
`load_factory_startup_post`, `save_pre`, `save_post`, `save_post_fail`, `undo_*`, `redo_*`) or in
`QUARTZ_HANDLER_NAMES` (`startup_post`, `shutdown_pre`, `shutdown_post`, `addon_enable_post`,
`addon_disable_post`).

| # | Name | # | Name | # | Name |
|---|---|---|---|---|---|
| 1 | `animation_playback_post` | 14 | `frame_change_pre` | 27 | `render_init` |
| 2 | `animation_playback_pre` | 15 | `load_factory_preferences_post` | 28 | `render_post` |
| 3 | `annotation_post` | 16 | `load_factory_startup_post` | 29 | `render_pre` |
| 4 | `annotation_pre` | 17 | `load_post` | 30 | `render_stats` |
| 5 | `blend_import_post` | 18 | `load_post_fail` | 31 | `render_write` |
| 6 | `blend_import_pre` | 19 | `load_pre` | 32 | `save_post` |
| 7 | `composite_cancel` | 20 | `object_bake_cancel` | 33 | `save_post_fail` |
| 8 | `composite_post` | 21 | `object_bake_complete` | 34 | `save_pre` |
| 9 | `composite_pre` | 22 | `object_bake_pre` | 35 | `translation_update_post` |
| 10 | `depsgraph_update_post` | 23 | `redo_post` | 36 | `undo_post` |
| 11 | `depsgraph_update_pre` | 24 | `redo_pre` | 37 | `undo_pre` |
| 12 | `exit_pre` | 25 | `render_cancel` | 38 | `version_update` |
| 13 | `frame_change_post` | 26 | `render_complete` | 39 | `xr_session_start_pre` |

### A.4 Translation contexts

`quartz.app.translations.contexts` (§1.2.5) has exactly these 60 fields, with these values (fact
`translations.contexts` from `data/blender_facts_judge.json`) **[O]**; the iteration order is the alphabetical
order of the fields, that of the fact **[I]** (Blender's native order was not probed). `default_real` is
`None`. `contexts_C_to_py` derives from these fields by the rule in §1.2.5.

| # | Field | Value | # | Field | Value |
|---|---|---|---|---|---|
| 1 | `amount` | `"Amount"` | 31 | `id_movieclip` | `"MovieClip"` |
| 2 | `color` | `"Color"` | 32 | `id_nodetree` | `"NodeTree"` |
| 3 | `constraint` | `"Constraint"` | 33 | `id_object` | `"Object"` |
| 4 | `countable` | `"Countable"` | 34 | `id_paintcurve` | `"PaintCurve"` |
| 5 | `default` | `"*"` | 35 | `id_palette` | `"Palette"` |
| 6 | `default_real` | `None` | 36 | `id_particlesettings` | `"ParticleSettings"` |
| 7 | `editor_filebrowser` | `"File browser"` | 37 | `id_pointcloud` | `"PointCloud"` |
| 8 | `editor_preferences` | `"Preferences"` | 38 | `id_scene` | `"Scene"` |
| 9 | `editor_python_console` | `"Python console"` | 39 | `id_screen` | `"Screen"` |
| 10 | `editor_view3d` | `"View3D"` | 40 | `id_sequence` | `"Sequence"` |
| 11 | `id_action` | `"Action"` | 41 | `id_shapekey` | `"Key"` |
| 12 | `id_armature` | `"Armature"` | 42 | `id_simulation` | `"Simulation"` |
| 13 | `id_brush` | `"Brush"` | 43 | `id_sound` | `"Sound"` |
| 14 | `id_cachefile` | `"CacheFile"` | 44 | `id_speaker` | `"Speaker"` |
| 15 | `id_camera` | `"Camera"` | 45 | `id_text` | `"Text"` |
| 16 | `id_collection` | `"Collection"` | 46 | `id_texture` | `"Texture"` |
| 17 | `id_curve` | `"Curve"` | 47 | `id_vfont` | `"VFont"` |
| 18 | `id_curves` | `"Curves"` | 48 | `id_volume` | `"Volume"` |
| 19 | `id_fs_linestyle` | `"FreestyleLineStyle"` | 49 | `id_windowmanager` | `"WindowManager"` |
| 20 | `id_gpencil` | `"GPencil"` | 50 | `id_workspace` | `"WorkSpace"` |
| 21 | `id_id` | `"ID"` | 51 | `id_world` | `"World"` |
| 22 | `id_image` | `"Image"` | 52 | `modifier` | `"Modifier"` |
| 23 | `id_lattice` | `"Lattice"` | 53 | `navigation` | `"Navigation"` |
| 24 | `id_library` | `"Library"` | 54 | `no_translation` | `"Do not translate"` |
| 25 | `id_light` | `"Light"` | 55 | `operator_default` | `"Operator"` |
| 26 | `id_lightprobe` | `"LightProbe"` | 56 | `plural` | `"Plural"` |
| 27 | `id_mask` | `"Mask"` | 57 | `render_layer` | `"Render Layer"` |
| 28 | `id_material` | `"Material"` | 58 | `time` | `"Time"` |
| 29 | `id_mesh` | `"Mesh"` | 59 | `ui_events_keymaps` | `"UI_Events_KeyMaps"` |
| 30 | `id_metaball` | `"Metaball"` | 60 | `unit` | `"Unit"` |

### A.5 Factory kwargs

`quartz.props.PROPERTY_KWARGS` (§1.6.1): for each factory, the kwargs accepted in 5.2.2, in dump order
(`props.<factory>.kwargs`) **[O]**; `meta` (`NATIVE_KWARGS`) is an addition by Quartz and is not in the table.
The defaults reproduce the dump text (`props.<factory>.defaults`) **[O]**; kwargs without a default
in the dump (`items`, `type`) are required (§1.6.1). The defaults cited in §1.6.1 (Float `default=0.0`,
`min/max/soft_min/soft_max=∓3.402823e+38`, `step=3`, `precision=2`; Int `min/soft_min=-2**31`,
`max/soft_max=2**31-1`, `step=1`; vectors `size=3`; `options={'ANIMATABLE'}`; `subtype='NONE'`;
`unit='NONE'`; String `maxlen=0`, `search_options={'SUGGESTION'}`; Enum `default=None`) are those of this
table. `RemoveProperty` is not part of `PROPERTY_KWARGS`: its signature in the dump is `(cls, attr)`.

| Factory | kwargs in dump order (`k=default`; `k` without `=` is required) |
|---|---|
| `BoolProperty` | `name=""`, `description=""`, `translation_context="*"`, `default=False`, `options={'ANIMATABLE'}`, `override=set()`, `tags=set()`, `subtype='NONE'`, `update=None`, `get=None`, `set=None`, `get_transform=None`, `set_transform=None` |
| `BoolVectorProperty` | `name=""`, `description=""`, `translation_context="*"`, `default=(False, False, False)`, `options={'ANIMATABLE'}`, `override=set()`, `tags=set()`, `subtype='NONE'`, `size=3`, `update=None`, `get=None`, `set=None`, `get_transform=None`, `set_transform=None` |
| `IntProperty` | `name=""`, `description=""`, `translation_context="*"`, `default=0`, `min=-2**31`, `max=2**31-1`, `soft_min=-2**31`, `soft_max=2**31-1`, `step=1`, `options={'ANIMATABLE'}`, `override=set()`, `tags=set()`, `subtype='NONE'`, `update=None`, `get=None`, `set=None`, `get_transform=None`, `set_transform=None` |
| `IntVectorProperty` | `name=""`, `description=""`, `translation_context="*"`, `default=(0, 0, 0)`, `min=-2**31`, `max=2**31-1`, `soft_min=-2**31`, `soft_max=2**31-1`, `step=1`, `options={'ANIMATABLE'}`, `override=set()`, `tags=set()`, `subtype='NONE'`, `size=3`, `update=None`, `get=None`, `set=None`, `get_transform=None`, `set_transform=None` |
| `FloatProperty` | `name=""`, `description=""`, `translation_context="*"`, `default=0.0`, `min=-3.402823e+38`, `max=3.402823e+38`, `soft_min=-3.402823e+38`, `soft_max=3.402823e+38`, `step=3`, `precision=2`, `options={'ANIMATABLE'}`, `override=set()`, `tags=set()`, `subtype='NONE'`, `unit='NONE'`, `update=None`, `get=None`, `set=None`, `get_transform=None`, `set_transform=None` |
| `FloatVectorProperty` | `name=""`, `description=""`, `translation_context="*"`, `default=(0.0, 0.0, 0.0)`, `min=-sys.float_info.max`, `max=sys.float_info.max`, `soft_min=-sys.float_info.max`, `soft_max=sys.float_info.max`, `step=3`, `precision=2`, `options={'ANIMATABLE'}`, `override=set()`, `tags=set()`, `subtype='NONE'`, `unit='NONE'`, `size=3`, `update=None`, `get=None`, `set=None`, `get_transform=None`, `set_transform=None` |
| `StringProperty` | `name=""`, `description=""`, `translation_context="*"`, `default=""`, `maxlen=0`, `options={'ANIMATABLE'}`, `override=set()`, `tags=set()`, `subtype='NONE'`, `update=None`, `get=None`, `set=None`, `get_transform=None`, `set_transform=None`, `search=None`, `search_options={'SUGGESTION'}` |
| `EnumProperty` | `items`, `name=""`, `description=""`, `translation_context="*"`, `default=None`, `options={'ANIMATABLE'}`, `override=set()`, `tags=set()`, `update=None`, `get=None`, `set=None`, `get_transform=None`, `set_transform=None` |
| `PointerProperty` | `type`, `name=""`, `description=""`, `translation_context="*"`, `options={'ANIMATABLE'}`, `override=set()`, `tags=set()`, `poll=None`, `update=None` |
| `CollectionProperty` | `type`, `name=""`, `description=""`, `translation_context="*"`, `options={'ANIMATABLE'}`, `override=set()`, `tags=set()` |

The limits of `FloatVectorProperty` appear in the dump as `sys.float_info.max` (docstring text);
Quartz stores floats as float32 and uses `∓3.402823e+38`, as in `FloatProperty` **[I]**.
