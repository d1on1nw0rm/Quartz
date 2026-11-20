from __future__ import annotations

import os
import threading
import time
import traceback
from dataclasses import dataclass, field

import numpy as np
from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QImage

from . import bridges
from .engine import RenderCancelled, RenderJob, RenderResult, execute_job, frame_path, prepare_job, save_result
from .settings import clean_settings, frame_list, get_settings

__all__ = ["RenderRecord", "RenderWorker", "RenderManager", "get_manager", "rgba_to_qimage", "HISTORY_LIMIT",
           "HISTORY_FULL_BYTES", "HISTORY_BYTES", "THUMB_SIZE"]

HISTORY_LIMIT = 24
HISTORY_FULL_BYTES = 256 * 1024 * 1024
HISTORY_BYTES = 768 * 1024 * 1024
THUMB_SIZE = 48


def rgba_to_qimage(rgba: np.ndarray) -> QImage:
    arr = np.asarray(rgba, float)
    h, w = arr.shape[:2]
    out = np.empty((h, w, 4), np.uint8)
    out[..., :3] = np.clip(np.round(arr[..., :3] * 255.0), 0, 255).astype(np.uint8)
    if arr.shape[2] > 3:
        out[..., 3] = np.clip(np.round(arr[..., 3] * 255.0), 0, 255).astype(np.uint8)
    else:
        out[..., 3] = 255
    data = np.ascontiguousarray(out)
    return QImage(data.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()


@dataclass(eq=False)
class RenderRecord:
    result: RenderResult
    target: str = "viewer"
    title: str = ""
    saved: list = field(default_factory=list)
    number: int = 0
    images: dict = field(default_factory=dict)
    thumb: QImage | None = None

    @property
    def compact(self) -> bool:
        return bool(self.result.compact)

    def image(self, name: str = "beauty") -> QImage:
        if name not in self.result.passes:
            name = "beauty"
        if self.compact:
            return self.result.image(name)
        if name not in self.images:
            self.images[name] = self.result.image(name)
        return self.images[name]

    def thumbnail(self) -> QImage:
        if self.thumb is None:
            from PySide6.QtCore import Qt
            self.thumb = self.result.image("beauty").scaled(
                THUMB_SIZE, THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
        return self.thumb

    def nbytes(self) -> int:
        cached = sum(int(img.sizeInBytes()) for img in self.images.values())
        return self.result.nbytes() + cached

    def make_compact(self) -> None:
        self.thumbnail()
        self.result.make_compact()
        self.images.clear()

    def summary(self) -> str:
        r = self.result
        frame = f"  frame {r.frame}" if r.frame is not None else ""
        return f"{self.title}  {r.width}x{r.height}  {r.seconds:.2f} s{frame}"


class RenderWorker(QObject):

    progress = Signal(float, str)
    bucket = Signal(object, QImage)
    done = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, job: RenderJob) -> None:
        super().__init__()
        self.job = job
        self._stop = threading.Event()

    def cancel(self) -> None:
        self._stop.set()

    def is_cancelled(self) -> bool:
        return self._stop.is_set()

    def _bucket(self, rect, rgba) -> None:
        self.bucket.emit(tuple(int(v) for v in rect), rgba_to_qimage(rgba))

    @Slot()
    def run(self) -> None:
        try:
            result = execute_job(self.job, progress=lambda f, s: self.progress.emit(float(f), str(s)),
                                 cancel=self._stop.is_set, on_bucket=self._bucket)
        except RenderCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)}")
        else:
            self.done.emit(result)


class RenderManager(QObject):

    started = Signal(object)
    progress = Signal(float, str)
    bucketReady = Signal(object, QImage)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    historyChanged = Signal()
    busyChanged = Signal(bool)

    def __init__(self, parent: QObject | None = None, threaded: bool = True, keep_history: bool = True) -> None:
        super().__init__(parent)
        self.threaded = threaded
        self.keep_history = keep_history
        self.history: list[RenderRecord] = []
        self.last_error = ""
        self._thread: QThread | None = None
        self._worker: RenderWorker | None = None
        self._queue: list = []
        self._pending = None
        self._scene = None
        self._request: dict = {}
        self._counter = 0
        self._busy = False
        self._last_progress = (0.0, "")
        self._started_at = 0.0
        self._old: list = []
        self._restore = None

    def is_running(self) -> bool:
        return self._busy

    def current_progress(self) -> tuple[float, str]:
        return self._last_progress

    def _set_busy(self, busy: bool) -> None:
        if busy != self._busy:
            self._busy = busy
            self.busyChanged.emit(busy)

    def render(self, scene=None, camera=None, settings: dict | None = None, *, width: int | None = None,
               height: int | None = None, target: str = "viewer", animation: bool | None = None,
               label: str = "") -> bool:
        if scene is None:
            from ..scene import get_scene
            scene = get_scene()
        s = clean_settings(settings) if settings is not None else get_settings(scene)
        request = {"scene": scene, "camera": camera, "settings": s, "width": width, "height": height,
                   "target": target, "label": label}
        anim = s["animation"] if animation is None else bool(animation)
        frames = frame_list(dict(s, animation=True)) if anim else [None]
        if self._busy:
            self._pending = (request, frames)
            self.cancel(clear_queue=True)
            return True
        self._begin(request, frames)
        return True

    def _begin(self, request: dict, frames: list) -> None:
        self._request = request
        self._queue = list(frames)
        animated = any(f is not None for f in frames)
        self._restore = (request["scene"], bridges.current_frame(request["scene"])) if animated else None
        self._set_busy(True)
        self._next()

    def _next(self) -> None:
        if not self._queue:
            self._finish_all()
            return
        frame = self._queue.pop(0)
        req = self._request
        scene = req["scene"]
        try:
            if frame is not None:
                bridges.evaluate_frame(scene, frame)
            job = prepare_job(scene, req["camera"], req["settings"], width=req["width"], height=req["height"],
                              frame=frame, label=req["label"], defer=self.threaded, evaluate=False)
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.failed.emit(self.last_error)
            self._queue = []
            self._finish_all()
            return
        self._started_at = time.perf_counter()
        self.started.emit({"width": job.width, "height": job.height, "camera": job.camera.name,
                           "frame": frame, "target": req["target"], "label": job.label,
                           "remaining": len(self._queue)})
        worker = RenderWorker(job)
        worker.progress.connect(self._on_progress)
        worker.bucket.connect(self._on_bucket)
        worker.done.connect(self._on_done)
        worker.failed.connect(self._on_failed)
        worker.cancelled.connect(self._on_cancelled)
        self._worker = worker
        if not self.threaded:
            worker.run()
            return
        thread = QThread()
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.cancelled.connect(thread.quit)
        self._thread = thread
        thread.start()

    def _release(self) -> None:
        thread = self._thread
        self._thread = None
        if thread is not None:
            thread.quit()
            thread.wait(5000)
        self._old.append((thread, self._worker))
        del self._old[:-2]
        self._worker = None

    def _on_progress(self, value: float, stage: str) -> None:
        self._last_progress = (value, stage)
        self.progress.emit(value, stage)

    def _on_bucket(self, rect, image: QImage) -> None:
        self.bucketReady.emit(rect, image)

    def _auto_save(self, result: RenderResult) -> list:
        s = result.settings
        saved = []
        if not s.get("auto_save") or not s.get("output_path"):
            return saved
        fmt = s.get("format", "png")
        path = frame_path(s["output_path"], result.frame, fmt)
        try:
            if save_result(result, path, fmt, "beauty", int(s.get("jpg_quality", 92))):
                saved.append(path)
            if s.get("save_passes"):
                for name in result.passes:
                    if name == "beauty":
                        continue
                    extra = frame_path(s["output_path"], result.frame, fmt, name)
                    if save_result(result, extra, fmt, name, int(s.get("jpg_quality", 92))):
                        saved.append(extra)
        except OSError as exc:
            self.last_error = f"Could not save: {exc}"
            self.failed.emit(self.last_error)
        return saved

    def _on_done(self, result: RenderResult) -> None:
        self._release()
        self._counter += 1
        req = self._request
        title = req.get("label") or result.label or result.camera or "Render"
        record = RenderRecord(result, req.get("target", "viewer"), f"{title} #{self._counter}",
                              self._auto_save(result), self._counter)
        if self.keep_history:
            self.history.insert(0, record)
            self.trim_history()
            self.historyChanged.emit()
        self.finished.emit(record)
        if self._pending is not None:
            self._queue = []
            self._finish_all()
            return
        self._next()

    def _on_failed(self, message: str) -> None:
        self._release()
        self.last_error = message
        self.failed.emit(message)
        self._queue = []
        self._finish_all()

    def _on_cancelled(self) -> None:
        self._release()
        self._queue = []
        self.cancelled.emit()
        self._finish_all()

    def _finish_all(self) -> None:
        restore, self._restore = self._restore, None
        if restore is not None and restore[1] is not None:
            bridges.evaluate_frame(restore[0], restore[1])
        self._set_busy(False)
        pending, self._pending = self._pending, None
        if pending is not None:
            request, frames = pending
            QTimer.singleShot(0, lambda: self._begin(request, frames))

    def cancel(self, clear_queue: bool = True) -> bool:
        if clear_queue:
            self._queue = []
        if self._worker is not None:
            self._worker.cancel()
            return True
        return False

    def trim_history(self) -> None:
        full = 0
        total = 0
        kept: list[RenderRecord] = []
        for i, rec in enumerate(self.history[:HISTORY_LIMIT]):
            size = rec.nbytes()
            if i > 0 and not rec.compact and full + size > HISTORY_FULL_BYTES:
                rec.make_compact()
                size = rec.nbytes()
            if i > 0 and total + size > HISTORY_BYTES:
                break
            if not rec.compact:
                full += size
            total += size
            kept.append(rec)
        self.history[:] = kept

    def history_bytes(self) -> int:
        return sum(r.nbytes() for r in self.history)

    def clear_history(self) -> None:
        self.history.clear()
        self.historyChanged.emit()

    def remove(self, record: RenderRecord) -> None:
        if record in self.history:
            self.history.remove(record)
            self.historyChanged.emit()

    def latest(self, target: str | None = None) -> RenderRecord | None:
        for r in self.history:
            if target is None or r.target == target:
                return r
        return None

    def wait(self, timeout: float = 120.0) -> bool:
        app = QCoreApplication.instance()
        end = time.perf_counter() + timeout
        while (self._busy or self._pending is not None) and time.perf_counter() < end:
            if app is not None:
                app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
            if self._thread is not None:
                self._thread.wait(10)
        if app is not None:
            app.processEvents()
        return not self._busy


_MANAGER: RenderManager | None = None


def get_manager() -> RenderManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = RenderManager()
    return _MANAGER


def output_folder_exists(path: str) -> bool:
    folder = os.path.dirname(os.path.abspath(path)) if path else ""
    return bool(folder) and os.path.isdir(folder)
