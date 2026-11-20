import os
from pathlib import Path

import pytest

PROJECT_ROOT: Path = Path(__file__).resolve().parents[1]
BLENDER_EXE: Path = Path(os.environ.get("QUARTZ_BLENDER_EXE", r"C:/Program Files/Blender Foundation/Blender 5.2/blender.exe"))
BLENDER_SCRIPTS: Path = Path(os.environ.get("QUARTZ_BLENDER_SCRIPTS", r"C:/Program Files/Blender Foundation/Blender 5.2/5.2/scripts"))
DUMP_PATH: Path = PROJECT_ROOT / "data" / "blender_api_dump.json"
USAGE_PATH: Path = PROJECT_ROOT / "data" / "bpy_usage.json"
FACTS_PATH: Path = PROJECT_ROOT / "data" / "blender_facts_judge.json"
FIXTURES_DIR: Path = PROJECT_ROOT / "tests" / "fixtures"


def pytest_configure(config) -> None:
    if getattr(config.option, "basetemp", None) is None:
        config.option.basetemp = str(PROJECT_ROOT / "tmp" / "pytest" / f"run-{os.getpid()}")


def pytest_collection_modifyitems(config, items) -> None:
    for item in items:
        if item.get_closest_marker("blender") is not None:
            if os.environ.get("QUARTZ_RUN_BLENDER") != "1" or not BLENDER_EXE.exists():
                item.add_marker(pytest.mark.skip(reason="blender not available"))
        if item.get_closest_marker("sweep") is not None:
            if os.environ.get("QUARTZ_RUN_SWEEP") != "1" or not BLENDER_SCRIPTS.exists():
                item.add_marker(pytest.mark.skip(reason="sweep not enabled"))
        if item.get_closest_marker("corpus") is not None:
            if not BLENDER_SCRIPTS.exists():
                item.add_marker(pytest.mark.skip(reason="blender scripts missing"))


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def blender_dump() -> dict:
    import json

    return json.loads(DUMP_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def blender_usage() -> dict:
    import json

    return json.loads(USAGE_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def blender_facts() -> dict:
    import json

    return json.loads(FACTS_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def blender_exe():
    if not BLENDER_EXE.exists():
        pytest.skip("blender executable missing")
    return BLENDER_EXE


@pytest.fixture
def blender_scripts():
    if not BLENDER_SCRIPTS.exists():
        pytest.skip("blender scripts missing")
    return BLENDER_SCRIPTS


@pytest.fixture
def qz_user_dir(monkeypatch, tmp_path):
    import quartz.app.paths as paths_mod

    paths_mod.reset()
    monkeypatch.setenv("QUARTZ_USER_DIR", str(tmp_path / "quartz_user"))
    p = paths_mod.user_dir()
    yield p
    paths_mod.reset()


@pytest.fixture
def qz(qz_user_dir):
    import quartz.testing as testing_mod

    with testing_mod.isolated(template="default") as s:
        yield s


@pytest.fixture
def qz_empty(qz_user_dir):
    import quartz.testing as testing_mod

    with testing_mod.isolated(template="empty") as s:
        yield s


@pytest.fixture
def bpy(qz):
    import importlib

    import quartz.compat as compat_mod

    compat_mod.activate(strict=True)
    try:
        yield importlib.import_module("bpy")
    finally:
        compat_mod.deactivate()


@pytest.fixture
def bpy_lenient(qz):
    import importlib

    import quartz.compat as compat_mod

    compat_mod.activate(strict=False)
    try:
        yield importlib.import_module("bpy")
    finally:
        compat_mod.deactivate()
