from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

STUDIO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if STUDIO_ROOT not in sys.path:
    sys.path.insert(0, STUDIO_ROOT)

import numpy as np
from PySide6.QtWidgets import QApplication

APP = QApplication.instance() or QApplication([sys.argv[0]])

from quartz_studio import tags
from quartz_studio.anim import core as anim_core
from quartz_studio.ext import runtime as ext_runtime
from quartz_studio.modeling import primitives as prim
from quartz_studio.rig import joints as jt, skin as sk
from quartz_studio.scene import Mesh, reset_scene


def _close(a, b, tol=1e-6) -> bool:
    return bool(np.allclose(np.asarray(a, float), np.asarray(b, float), atol=tol, rtol=0.0))


def _aim(obj):
    z = obj.world_linear()[:, 2]
    return z / np.linalg.norm(z)


def _build():
    s = reset_scene()
    mover = s.objects[0]
    mover.position = np.array([0.0, 0.0, 0.0])
    anim_core.insert_key(mover, "position.x", 0, 0.0, interp="linear", scene=s)
    anim_core.insert_key(mover, "position.x", 10, 100.0, interp="linear", scene=s)
    watcher = s.add_object("Watcher", Mesh.cube(50.0))
    watcher.position = np.array([0.0, 0.0, -100.0])
    tags.add_tag(watcher, "target", target=mover.name)
    chain = jt.create_chain(s, [(0, 0, 0), (0, 100, 0), (0, 200, 0)])
    limb = s.add_object("Limb", prim.cylinder(20.0, 200.0, 12, 12))
    limb.position = np.array([0.0, 100.0, 0.0])
    limb = sk.bind_skin(s, limb, chain)
    anim_core.insert_key(chain[1], "rotation.z", 0, 0.0, interp="linear", scene=s)
    anim_core.insert_key(chain[1], "rotation.z", 10, 60.0, interp="linear", scene=s)
    scripted = s.add_object("Scripted", Mesh.cube(10.0))
    tags.add_tag(scripted, "python", code="op.position = np.array([0.0, frame * 5.0, 0.0])\n")
    return s, mover, watcher, limb, scripted


def test_all_stages_run_and_report():
    s, *_ = _build()
    report = ext_runtime.evaluate_frame(s, 0)
    assert report["ran"] == ["anim", "tags", "rig", "scripting"], report
    assert report["errors"] == {}, report["errors"]
    assert report["skipped"] == []
    assert report["results"]["scripting"]["count"] == 1
    assert report["results"]["scripting"]["failed"] == 0


def test_effects_at_two_frames():
    s, mover, watcher, limb, scripted = _build()
    rest = limb.mesh.points.copy()

    ext_runtime.evaluate_frame(s, 0)
    assert _close(mover.position, [0.0, 0.0, 0.0])
    assert _close(_aim(watcher), [0.0, 0.0, 1.0], 1e-6)
    assert _close(limb.mesh.points, rest, 1e-6)
    assert _close(scripted.position, [0.0, 0.0, 0.0])

    report = ext_runtime.evaluate_frame(s, 10)
    assert report["errors"] == {}, report["errors"]
    assert _close(mover.position, [100.0, 0.0, 0.0])
    expected = np.array([100.0, 0.0, 100.0]) / np.linalg.norm([100.0, 0.0, 100.0])
    assert _close(_aim(watcher), expected, 1e-6)
    assert report["results"]["rig"]["deformed"] >= 1
    assert not _close(limb.mesh.points, rest, 1e-3)
    assert _close(scripted.position, [0.0, 50.0, 0.0])

    ext_runtime.evaluate_frame(s, 5)
    assert _close(mover.position, [50.0, 0.0, 0.0])
    expected = np.array([50.0, 0.0, 100.0]) / np.linalg.norm([50.0, 0.0, 100.0])
    assert _close(_aim(watcher), expected, 1e-6)
    assert _close(scripted.position, [0.0, 25.0, 0.0])


def test_failing_stage_does_not_stop_others():
    s, mover, watcher, limb, scripted = _build()
    original = ext_runtime._RUNNERS["tags"]

    def boom(mod, scene, frame):
        raise RuntimeError("tags exploded")

    ext_runtime._RUNNERS["tags"] = boom
    try:
        report = ext_runtime.evaluate_frame(s, 10)
    finally:
        ext_runtime._RUNNERS["tags"] = original
    assert "tags" in report["errors"] and "tags exploded" in report["errors"]["tags"]
    assert report["ran"] == ["anim", "rig", "scripting"]
    assert _close(mover.position, [100.0, 0.0, 0.0])
    assert _close(scripted.position, [0.0, 50.0, 0.0])


def test_missing_package_is_skipped():
    s, *_ = _build()
    original = ext_runtime._load

    def fake(name):
        return None if name == "rig" else original(name)

    ext_runtime._load = fake
    try:
        report = ext_runtime.evaluate_frame(s, 3)
    finally:
        ext_runtime._load = original
    assert report["skipped"] == ["rig"]
    assert "rig" not in report["ran"] and report["errors"] == {}


def test_python_tag_error_is_reported_not_raised():
    s, mover, watcher, limb, scripted = _build()
    tags.add_tag(scripted, "python", code="raise ValueError('bad tag')\n")
    report = ext_runtime.evaluate_frame(s, 4)
    assert "scripting" in report["ran"]
    assert report["results"]["scripting"]["failed"] == 1
    assert "bad tag" in report["results"]["scripting"]["errors"][0]
    assert _close(scripted.position, [0.0, 20.0, 0.0])


def _run_as_script() -> int:
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    tests.sort(key=lambda item: item[1].__code__.co_firstlineno)
    failures = 0
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:
            failures += 1
            print(f"FAIL {name}: {type(exc).__name__}: {exc}".encode("ascii", "replace").decode())
        else:
            print(f"ok   {name}")
    print(f"{len(tests) - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_run_as_script())
