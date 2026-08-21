"""Background execution for the desktop app.

Every long job — a Maps search, a website scan, a phone lookup, an email run —
is a plain callable that takes ``progress`` and ``on_event`` callbacks. This
module runs one on a :class:`QThread` and turns those callbacks into Qt
signals, so page code only ever touches widgets from the GUI thread.

Cancellation is cooperative and rides along on the progress callback: the
pipeline calls ``progress`` constantly, so :class:`RunControl` uses that call
as its checkpoint — blocking there while the run is paused and raising
:class:`Cancelled` once the user hits Stop. The pipeline's own ``finally``
blocks still run, so the browser is closed and partial results are exported.
"""

from __future__ import annotations

import threading
import traceback
from typing import Any, Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal


class Cancelled(Exception):
    """Raised inside a worker thread once the user asks it to stop."""


class RunControl:
    """Pause / stop switch shared between the GUI thread and one worker."""

    def __init__(self) -> None:
        self._resumed = threading.Event()
        self._resumed.set()
        self._stop = threading.Event()
        # Cancellation fires exactly once. The pipeline saves partial results
        # from its own `finally` blocks, and those call progress() too — if
        # every later call kept raising, the stop would abort the very cleanup
        # that writes the CSV.
        self._raised = False

    # -- driven from the GUI thread --------------------------------------
    def pause(self) -> None:
        self._resumed.clear()

    def resume(self) -> None:
        self._resumed.set()

    def toggle_pause(self) -> bool:
        """Flip paused state; returns True when now paused."""
        if self.paused:
            self.resume()
            return False
        self.pause()
        return True

    def stop(self) -> None:
        self._stop.set()
        # A paused job has to wake up before it can notice the stop.
        self._resumed.set()

    @property
    def paused(self) -> bool:
        return not self._resumed.is_set()

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    # -- called from the worker thread ------------------------------------
    def checkpoint(self) -> None:
        """Block while paused; raise :class:`Cancelled` the first time stopped.

        After that first raise the run is unwinding through its cleanup, so
        this becomes a no-op and lets the exports in those ``finally`` blocks
        finish.
        """
        if self._raised:
            return
        if self._stop.is_set():
            self._raised = True
            raise Cancelled()
        # Wake up periodically so a stop during a pause is noticed promptly.
        while not self._resumed.wait(0.1):
            if self._stop.is_set():
                self._raised = True
                raise Cancelled()
        if self._stop.is_set():
            self._raised = True
            raise Cancelled()


ProgressFn = Callable[[str], None]
EventFn = Callable[[Any], None]
JobFn = Callable[..., Any]


class Job(QObject):
    """Runs one callable on a worker thread and reports back with signals."""

    message = Signal(str)      # a progress line
    event = Signal(object)     # a ScanEvent (or any structured update)
    finished = Signal(object)  # the callable's return value
    failed = Signal(str)       # an unexpected error
    cancelled = Signal()       # stopped on request
    ended = Signal()           # always last, whatever the outcome

    def __init__(self, fn: JobFn, control: RunControl) -> None:
        super().__init__()
        self._fn = fn
        self._control = control

    def run(self) -> None:
        def progress(text: str) -> None:
            self._control.checkpoint()
            self.message.emit(str(text))

        def on_event(payload: Any) -> None:
            self._control.checkpoint()
            self.event.emit(payload)

        try:
            result = self._fn(progress=progress, on_event=on_event)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001 - a crash must not kill the app
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            self.message.emit(traceback.format_exc(limit=4))
        else:
            self.finished.emit(result)
        finally:
            self.ended.emit()


class JobRunner(QObject):
    """Owns the thread + job pair for one page, one job at a time."""

    message = Signal(str)
    event = Signal(object)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()
    ended = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._thread: Optional[QThread] = None
        self._job: Optional[Job] = None
        self.control = RunControl()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, fn: JobFn) -> bool:
        """Run ``fn`` in the background. Returns False if one is already going."""
        if self.running:
            return False
        self.control = RunControl()
        self._thread = QThread()
        self._job = Job(fn, self.control)
        self._job.moveToThread(self._thread)

        self._thread.started.connect(self._job.run)
        self._job.message.connect(self.message)
        self._job.event.connect(self.event)
        self._job.finished.connect(self.finished)
        self._job.failed.connect(self.failed)
        self._job.cancelled.connect(self.cancelled)
        self._job.ended.connect(self._cleanup)
        self._thread.start()
        return True

    def _cleanup(self) -> None:
        thread, self._thread = self._thread, None
        self._job = None
        if thread is not None:
            thread.quit()
            thread.wait(5000)
        self.ended.emit()

    # -- controls ---------------------------------------------------------
    def toggle_pause(self) -> bool:
        return self.control.toggle_pause()

    def stop(self) -> None:
        self.control.stop()

    def wait(self, msecs: int = 10000) -> None:
        """Block until the current job finishes — used when closing the app."""
        thread = self._thread
        if thread is not None:
            thread.wait(msecs)
