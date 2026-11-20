from __future__ import annotations

import contextlib
import inspect
import io
import math
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

from ..ext import store
from . import api
from .runner import ScriptTimeout, Watchdog, register_source

__all__ = [
    "PYTHON_TAG",
    "PRIORITIES",
    "TagType",
    "TagRunResult",
    "TAG_TYPES",
    "register_tag_type",
    "unregister_tag_type",
    "tag_types",
    "forwarded_specs",
    "run_python_tags",
    "run_tags",
    "FrameDriver",
    "FRAME_KEYS",
    "ANIM_KEY",
    "tag_timeout",
    "set_tag_timeout",
]

PYTHON_TAG = "python"
FRAME_KEYS = ("frame", "current_frame", "time")
ANIM_KEY = "anim"
PRIORITIES = ("Initial", "Animation", "Expressions", "Dynamics", "Generators")
DEFAULT_PRIORITY = "Expressions"
RESERVED_FIELDS = ("type", "name", "enabled")
TAG_TIMEOUT_KEY = "tag_timeout"
DEFAULT_TAG_TIMEOUT = 10.0


def tag_timeout() -> float | None:
    from . import paths
    value = paths.read_settings().get(TAG_TIMEOUT_KEY, DEFAULT_TAG_TIMEOUT)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return DEFAULT_TAG_TIMEOUT
    return value if value > 0 else None


def set_tag_timeout(seconds: float | None) -> float:
    from . import paths
    value = 0.0 if seconds is None else max(0.0, float(seconds))
    paths.update_settings(TAG_TIMEOUT_KEY, value)
    return value


@dataclass
class TagType:
    id: str
    label: str
    defaults: dict = field(default_factory=dict)
    run: Callable | None = None
    owner: str = ""
    description: str = ""


@dataclass
class TagRunResult:
    object_name: str
    index: int
    tag_name: str
    tag_type: str
    ok: bool
    output: str = ""
    error: str = ""


TAG_TYPES: dict[str, TagType] = {}
_FORWARDED: dict[str, Any] = {}
_CODE_CACHE: dict[tuple[str, str], Any] = {}


def _tags_registry():
    try:
        from ..tags import registry as treg
    except Exception:
        return None
    return treg


def _param_kind(key: str, value: Any) -> str:
    if isinstance(value, (bool, np.bool_)):
        return "bool"
    if isinstance(value, (int, np.integer)):
        return "int"
    if isinstance(value, (float, np.floating)):
        return "float"
    if isinstance(value, str):
        return "code" if key == "code" else "text"
    if isinstance(value, (list, tuple, np.ndarray)):
        vals = list(np.asarray(value).reshape(-1)) if isinstance(value, np.ndarray) else list(value)
        if 2 <= len(vals) <= 4 and all(isinstance(v, (int, float, np.integer, np.floating))
                                       and not isinstance(v, bool) for v in vals):
            return "vector"
    return "data"


def _tag_params(treg, defaults: dict) -> tuple:
    out = []
    for key, value in defaults.items():
        if key in RESERVED_FIELDS:
            continue
        kind = _param_kind(key, value)
        label = str(key).replace("_", " ").title()
        if kind == "vector":
            default = [float(v) for v in np.asarray(value, float).reshape(-1)]
        elif kind == "data":
            default = store.to_json(value)
        else:
            default = value.item() if isinstance(value, np.generic) else value
        out.append(treg.TagParam(str(key), label, kind, default))
    return tuple(out)


def _forward_to_tags_package(spec: TagType) -> Any:
    treg = _tags_registry()
    if treg is None:
        return None
    current = treg.TAG_SPECS.get(spec.id)
    if current is not None and _FORWARDED.get(spec.id) is not current:
        return None
    try:
        tspec = treg.TagSpec(
            id=spec.id, label=spec.label, category="Programming Tags",
            params=_tag_params(treg, spec.defaults), icon="python",
            description=spec.description or f"Plugin tag from {spec.owner or 'a plugin'}",
            extra={"scripting_owner": spec.owner},
        )
    except (TypeError, ValueError):
        return None
    treg.TAG_SPECS.pop(spec.id, None)
    treg.register_tag(tspec)
    _FORWARDED[spec.id] = tspec
    return tspec


def _withdraw_from_tags_package(tag_id: str) -> None:
    tspec = _FORWARDED.pop(tag_id, None)
    treg = _tags_registry()
    if tspec is None or treg is None:
        return
    if treg.TAG_SPECS.get(tag_id) is tspec:
        treg.TAG_SPECS.pop(tag_id, None)


def forwarded_specs() -> dict:
    return dict(_FORWARDED)


def register_tag_type(tag_id: str, label: str, defaults: dict | None = None,
                      run: Callable | None = None, owner: str = "",
                      description: str = "") -> TagType:
    tag_id = str(tag_id)
    if not tag_id:
        raise ValueError("tag type id is required")
    if tag_id in TAG_TYPES and TAG_TYPES[tag_id].owner != owner:
        raise ValueError(f"tag type {tag_id!r} registered twice")
    treg = _tags_registry()
    if (treg is not None and tag_id != PYTHON_TAG and tag_id in treg.TAG_SPECS
            and _FORWARDED.get(tag_id) is not treg.TAG_SPECS[tag_id]):
        raise ValueError(f"tag type {tag_id!r} is a built-in tag")
    if run is not None and not callable(run):
        raise TypeError("run must be callable")
    spec = TagType(tag_id, str(label), dict(defaults or {}), run, owner, description)
    TAG_TYPES[tag_id] = spec
    if tag_id != PYTHON_TAG:
        _forward_to_tags_package(spec)
    return spec


def unregister_tag_type(tag_id: str) -> bool:
    if tag_id == PYTHON_TAG:
        return False
    _withdraw_from_tags_package(tag_id)
    return TAG_TYPES.pop(tag_id, None) is not None


def tag_types() -> tuple[TagType, ...]:
    return tuple(TAG_TYPES.values())


def _compiled(code: str, filename: str):
    key = (filename, code)
    hit = _CODE_CACHE.get(key)
    if hit is None:
        if len(_CODE_CACHE) > 256:
            _CODE_CACHE.clear()
        register_source(filename, code)
        hit = compile(code, filename, "exec")
        _CODE_CACHE[key] = hit
    return hit


def _format(exc: BaseException) -> str:
    tb = exc.__traceback__
    if tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    if isinstance(exc, SyntaxError):
        return "".join(traceback.format_exception_only(type(exc), exc))
    return "".join(traceback.format_exception(type(exc), exc, tb))


def _tag_list(obj) -> list:
    value = store.get_object(obj, "tags", [])
    return value if isinstance(value, list) else []


def _call_with_names(fn: Callable, values: dict):
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return fn()
    args = []
    kwargs = {}
    for p in sig.parameters.values():
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        if p.name in values:
            if p.kind == p.POSITIONAL_ONLY:
                args.append(values[p.name])
            else:
                kwargs[p.name] = values[p.name]
        elif p.default is p.empty:
            raise TypeError(f"{getattr(fn, '__name__', 'main')}() asks for {p.name!r}; "
                            f"it can take {', '.join(values)}")
    return fn(*args, **kwargs)


def _timeout_text(exc: BaseException, limit: float | None) -> str:
    text = _format(exc).rstrip("\n")
    return f"{text}: the tag ran longer than {limit:g} s and was stopped\n"


def _run_python(obj, index: int, tag: dict, scene, frame: float,
                limit: float | None = None) -> TagRunResult:
    name = str(tag.get("name") or "Python")
    filename = f"<python tag {obj.name}:{index}>"
    out = io.StringIO()
    values = {"op": obj, "doc": scene, "frame": frame, "quartz": api, "np": np, "tag": dict(tag)}
    ns = {"__name__": "__python_tag__", "__builtins__": __builtins__}
    ns.update(values)
    try:
        code = _compiled(str(tag.get("code", "")), filename)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), Watchdog(limit):
            exec(code, ns)
            main = ns.get("main")
            if callable(main):
                _call_with_names(main, values)
    except ScriptTimeout as exc:
        return TagRunResult(obj.name, index, name, PYTHON_TAG, False, out.getvalue(), _timeout_text(exc, limit))
    except Exception as exc:
        return TagRunResult(obj.name, index, name, PYTHON_TAG, False, out.getvalue(), _format(exc))
    return TagRunResult(obj.name, index, name, PYTHON_TAG, True, out.getvalue())


def _run_custom(spec: TagType, obj, index: int, tag: dict, scene, frame: float,
                limit: float | None = None) -> TagRunResult:
    name = str(tag.get("name") or spec.label)
    out = io.StringIO()
    merged = dict(spec.defaults)
    merged.update(tag)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), Watchdog(limit):
            spec.run(obj, merged, scene, frame)
    except ScriptTimeout as exc:
        return TagRunResult(obj.name, index, name, spec.id, False, out.getvalue(), _timeout_text(exc, limit))
    except Exception as exc:
        return TagRunResult(obj.name, index, name, spec.id, False, out.getvalue(), _format(exc))
    return TagRunResult(obj.name, index, name, spec.id, True, out.getvalue())


def _priority(tag: dict) -> int:
    value = str(tag.get("priority") or DEFAULT_PRIORITY)
    return PRIORITIES.index(value) if value in PRIORITIES else PRIORITIES.index(DEFAULT_PRIORITY)


def _jobs(scene, include_custom: bool) -> list:
    jobs = []
    order = 0
    for obj in list(scene.objects):
        if not getattr(obj, "enabled", True):
            continue
        for index, tag in enumerate(list(_tag_list(obj))):
            if not isinstance(tag, dict) or not tag.get("enabled", True):
                continue
            kind = tag.get("type")
            if kind == PYTHON_TAG:
                jobs.append((_priority(tag), order, obj, index, tag, None))
            elif include_custom:
                spec = TAG_TYPES.get(kind)
                if spec is not None and spec.run is not None:
                    jobs.append((_priority(tag), order, obj, index, tag, spec))
            order += 1
    jobs.sort(key=lambda j: (j[0], j[1]))
    return jobs


def _walk(scene, frame: float, include_custom: bool) -> list[TagRunResult]:
    results: list[TagRunResult] = []
    jobs = _jobs(scene, include_custom)
    if not jobs:
        return results
    limit = tag_timeout()
    with api.bind_scene(scene), api.suppress_undo(scene):
        for _prio, _order, obj, index, tag, spec in jobs:
            if obj not in scene.objects or not getattr(obj, "enabled", True):
                continue
            if spec is None:
                results.append(_run_python(obj, index, tag, scene, frame, limit))
            else:
                results.append(_run_custom(spec, obj, index, tag, scene, frame, limit))
        if results:
            changed = getattr(scene, "changed", None)
            if changed is not None:
                changed.emit()
    return results


def run_python_tags(scene=None, frame: float | None = None) -> list[TagRunResult]:
    scene = api.document() if scene is None else scene
    frame = api.current_frame(scene) if frame is None else float(frame)
    return _walk(scene, frame, include_custom=False)


def run_tags(scene=None, frame: float | None = None) -> list[TagRunResult]:
    scene = api.document() if scene is None else scene
    frame = api.current_frame(scene) if frame is None else float(frame)
    return _walk(scene, frame, include_custom=True)


register_tag_type(PYTHON_TAG, "Python", {"code": "def main(op, frame):\n    pass\n",
                                         "priority": DEFAULT_PRIORITY},
                  None, "scripting", "Runs Python code every frame with op, doc, frame and quartz")


def _anim_frame(scene) -> float | None:
    raw = store.get_scene_data(scene, ANIM_KEY)
    if not isinstance(raw, dict) or "frame" not in raw:
        return None
    try:
        value = float(raw["frame"])
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


class FrameDriver:

    def __init__(self, scene=None, include_custom: bool = True, deferred: bool | None = None,
                 follow_global: bool = False) -> None:
        self.follow_global = bool(follow_global and scene is None)
        self._scene = None if self.follow_global else (api.document() if scene is None else scene)
        self.include_custom = include_custom
        self.enabled = True
        self.last_results: list[TagRunResult] = []
        self.runs = 0
        self._busy = False
        self._installed = False
        self._pending: tuple | None = None
        self._timer = None
        self._last_anim: dict[int, float | None] = {id(self.scene): _anim_frame(self.scene)}
        if deferred is None:
            try:
                from PySide6.QtCore import QCoreApplication
                deferred = QCoreApplication.instance() is not None
            except ImportError:
                deferred = False
        self.deferred = bool(deferred)
        self.install()

    def install(self) -> None:
        if not self._installed:
            store._LISTENERS.append(self._on_store)
            self._installed = True

    def uninstall(self) -> None:
        if self._installed:
            try:
                store._LISTENERS.remove(self._on_store)
            except ValueError:
                pass
            self._installed = False
        self._pending = None
        if self._timer is not None:
            self._timer.stop()

    @property
    def installed(self) -> bool:
        return self._installed

    @property
    def scene(self):
        if self.follow_global:
            from ..scene import get_scene
            return get_scene()
        return self._scene

    def _on_store(self, owner, key: str) -> None:
        scene = self.scene
        if owner is not scene or not self.enabled or self._busy:
            return
        if key == ANIM_KEY:
            frame = _anim_frame(scene)
            if frame is None or frame == self._last_anim.get(id(scene)):
                return
            self._last_anim = {id(scene): frame}
            self._schedule(scene, frame)
        elif key in FRAME_KEYS:
            self._schedule(scene, api.current_frame(scene))

    def _schedule(self, scene, frame: float) -> None:
        if not self.deferred:
            self.run(frame, scene)
            return
        self._pending = (scene, frame)
        if self._timer is None:
            from PySide6.QtCore import QTimer
            self._timer = QTimer()
            self._timer.setSingleShot(True)
            self._timer.setInterval(0)
            self._timer.timeout.connect(self.flush)
        self._timer.start()

    def flush(self) -> list[TagRunResult]:
        if self._pending is None:
            return self.last_results
        (scene, frame), self._pending = self._pending, None
        if not self.enabled or not self._installed or scene is not self.scene:
            return self.last_results
        return self.run(frame, scene)

    def run(self, frame: float | None = None, scene=None) -> list[TagRunResult]:
        if self._busy:
            return self.last_results
        self._busy = True
        try:
            fn = run_tags if self.include_custom else run_python_tags
            self.last_results = fn(self.scene if scene is None else scene, frame)
            self.runs += 1
        finally:
            self._busy = False
        return self.last_results
