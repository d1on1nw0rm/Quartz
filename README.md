# Quartz

A 3D modeling program. Author: **D1on1n**.

Quartz has two parts. The core, in `quartz/`, is a headless 3D application library with a `bpy`-shaped API (data-blocks,
meshes, operators, properties, undo). The interface, in `studio/`, is Quartz Studio, a PySide6 desktop app with a
Cinema 4D style viewport.

## Folders

| Folder | What it holds |
|---|---|
| `quartz/` | The headless core library. |
| `studio/` | Quartz Studio, the desktop interface, and its build script. |
| `tests/` | Tests for the core. |
| `tools/` | Scripts that dump the Blender API and scan `bpy` usage. |
| `data/` | The Blender API dump and reference facts the tests read. |
| `docs/` | Architecture, public contracts, design proposals and research notes. |
| `coord/` | Notes and helper scripts from the multi-agent build. |

## Requirements

- Windows.
- Python 3.13 or newer for the core, 3.14 or newer for the studio.
- numpy for the core; PySide6 6.12 and PyInstaller for the studio.

## How to run

Run `Quartz.exe` in this folder. It needs no install.

From source, in `studio/`:

```
.venv\Scripts\python.exe -m quartz_studio
```

## How to build

```
powershell -ExecutionPolicy Bypass -File studio\build.ps1
```

It writes `Quartz.exe` to this folder. The file icon is `quartz.ico`. The window icon is
`studio\assets\quartzInstance.ico`.

## How to test

Core tests, from this folder:

```
.venv\Scripts\python.exe -m pytest -q
```

Studio tests, from `studio/`. They use offscreen Qt and run as modules, one per file:

```
.venv\Scripts\python.exe -m tests.test_smoke
.venv\Scripts\python.exe -m tests.test_wiring
```

The full list is in `studio\README.md`.
