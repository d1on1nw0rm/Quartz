from __future__ import annotations

import importlib
import traceback

__all__ = ["STAGES", "evaluate_frame"]

STAGES = ("anim", "tags", "rig", "scripting")


def _load(name: str):
    try:
        return importlib.import_module(f"quartz_studio.{name}")
    except Exception:
        return None


def _fps(scene) -> float:
    anim = _load("anim")
    if anim is None:
        return 30.0
    try:
        value = float(anim.core.fps(scene))
    except Exception:
        return 30.0
    return value if value > 0 else 30.0


def _run_anim(mod, scene, frame: float):
    return len(mod.core.evaluate(scene, frame, emit=False))


def _run_tags(mod, scene, frame: float):
    return len(mod.evaluate_tags(scene, frame, fps=_fps(scene)))


def _run_rig(mod, scene, frame: float):
    return dict(mod.runtime.evaluate_rig(scene, emit=False))


def _run_scripting(mod, scene, frame: float):
    results = mod.run_tags(scene, frame)
    failed = [r for r in results if not r.ok]
    return {"count": len(results), "failed": len(failed),
            "errors": [str(r.error) for r in failed]}


_RUNNERS = {
    "anim": _run_anim,
    "tags": _run_tags,
    "rig": _run_rig,
    "scripting": _run_scripting,
}


def evaluate_frame(scene, frame: float, emit: bool = True) -> dict:
    frame = float(frame)
    report = {"frame": frame, "ran": [], "skipped": [], "errors": {}, "results": {}}
    for name in STAGES:
        mod = _load(name)
        if mod is None:
            report["skipped"].append(name)
            continue
        try:
            report["results"][name] = _RUNNERS[name](mod, scene, frame)
        except Exception as exc:
            report["errors"][name] = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            continue
        report["ran"].append(name)
    if emit and report["ran"]:
        sig = getattr(scene, "changed", None)
        if sig is not None:
            try:
                sig.emit()
            except Exception as exc:
                report["errors"]["emit"] = str(exc)
    return report
