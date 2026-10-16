"""Qt worker boundary for product-adapted case execution."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from PySide6 import QtCore

from panelsolver.core import SchedulerCancelled

from .solver_spec import CaseRow, GuiRunRequest, GuiRunResult, RunCasesCallback
from .summary_export import SummaryCsvSnapshot, write_summary_snapshot


class ThreadWorker(QtCore.QObject):
    """Run once on a worker QThread, then return to the GUI thread.

    PySide releases a wrapped QObject's Python state in the thread that destroys
    it. Destroying a worker on its own QThread can deadlock (``~QObject`` holds
    Qt's connection lock while a Python override waits for the GIL that the GUI
    thread holds) and releases Python references off the GUI thread. Moving the
    worker back before its thread finishes lets ``prepare_worker_thread`` delete
    it on the GUI thread instead.
    """

    def __init__(self) -> None:
        super().__init__()
        self._gui_thread = self.thread()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            self._execute()
        finally:
            self.moveToThread(self._gui_thread)

    def _execute(self) -> None:
        raise NotImplementedError


def prepare_worker_thread(
    parent: QtCore.QObject,
    worker: ThreadWorker,
    terminal_signals: Sequence[QtCore.SignalInstance],
    on_finished: Callable[[], None],
) -> QtCore.QThread:
    """Wire ``worker`` to a new QThread; the caller connects results and starts it.

    Each terminal signal quits the thread. When it finishes, ``on_finished`` runs
    on the GUI thread, followed by deletion of the worker and the thread there.
    """
    thread = QtCore.QThread(parent)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    for signal in terminal_signals:
        signal.connect(thread.quit)
    thread.finished.connect(on_finished)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    return thread


class CaseRunWorker(ThreadWorker):
    """Run one adapter callback and expose only queued Qt signals to widgets."""

    log = QtCore.Signal(str)
    progress = QtCore.Signal(int, int)
    completed = QtCore.Signal(object)
    failed = QtCore.Signal(str)
    canceled = QtCore.Signal()

    def __init__(
        self,
        run_cases: RunCasesCallback,
        rows: Sequence[CaseRow],
        workers: int,
        checkpoint_every_cases: int,
        output_path: str | Path,
        vtp_dir: str | Path,
    ) -> None:
        super().__init__()
        if not callable(run_cases):
            raise TypeError("run_cases must be callable")
        self._run_cases = run_cases
        self._rows = tuple(rows)
        self._workers = workers
        self._checkpoint_every_cases = checkpoint_every_cases
        self._output_path = Path(output_path)
        self._vtp_dir = Path(vtp_dir)
        self._cancel_event = threading.Event()

    def _execute(self) -> None:
        """Execute until completion, primary failure, or boundary cancellation."""
        try:
            request = GuiRunRequest(
                rows=self._rows,
                workers=self._workers,
                checkpoint_every_cases=self._checkpoint_every_cases,
                output_path=self._output_path,
                vtp_dir=self._vtp_dir,
                log=self.log.emit,
                progress=self.progress.emit,
                cancel_requested=self._cancel_event.is_set,
            )
            result = self._run_cases(request)
            if not isinstance(result, GuiRunResult):
                raise TypeError("run_cases must return a GuiRunResult")
        except SchedulerCancelled:
            self.canceled.emit()
            return
        except Exception as exc:
            self.failed.emit(str(exc))
            return

        if self._cancel_event.is_set() and result.unsaved_summary_csv is None:
            self.canceled.emit()
            return
        self.completed.emit(result)

    def cancel(self) -> None:
        """Request cancellation; the adapter observes it at case boundaries."""
        self._cancel_event.set()


class SummaryExportWorker(ThreadWorker):
    """Save a retained CSV without solving or blocking the GUI thread."""

    completed = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, path: Path, snapshot: SummaryCsvSnapshot, protected_paths):
        super().__init__()
        self._path = path
        self._snapshot = snapshot
        self._protected_paths = protected_paths

    def _execute(self) -> None:
        try:
            path = write_summary_snapshot(
                self._path, self._snapshot, self._protected_paths
            )
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(path)


__all__ = (
    "CaseRunWorker",
    "SummaryExportWorker",
    "ThreadWorker",
    "prepare_worker_thread",
)
