"""Read-only sectional definitions and snapshot-bound batch results in Qt."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from types import MappingProxyType

from PySide6 import QtCore, QtWidgets

from .cases_panel import CasesPanel
from .csv_writer import validate_csv_output_path
from .gui_components import FlowLayout
from .gui_theme import set_semantic_property
from .path_resolution import default_summary_output_path
from .sectional_batch import (
    SectionalBatchResult,
    sectional_protected_paths,
    write_sectional_csv,
)
from .sectional_definitions import SectionalDefinition, read_sectional_definitions
from .solver_spec import GuiSectionalRunRequest, RunSectionalCasesCallback, SolverSpec


class _ReadOnlyModel(QtCore.QAbstractTableModel):
    """Display immutable records without per-cell widgets or numerical copies."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.columns: tuple[str, ...] = ()
        self.rows: tuple[Mapping[str, object], ...] = ()

    def replace(self, columns, rows) -> None:
        self.beginResetModel()
        self.columns = tuple(columns)
        self.rows = tuple(rows)
        self.endResetModel()

    def rowCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.rows)

    def columnCount(self, parent=None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.columns)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        value = self.rows[index.row()][self.columns[index.column()]]
        if role in (
            QtCore.Qt.ItemDataRole.DisplayRole,
            QtCore.Qt.ItemDataRole.ToolTipRole,
        ):
            if value is None:
                return ""
            return f"{value:.10g}" if isinstance(value, float) else str(value)
        if role == QtCore.Qt.ItemDataRole.TextAlignmentRole:
            horizontal = (
                QtCore.Qt.AlignmentFlag.AlignRight
                if isinstance(value, (int, float)) and not isinstance(value, bool)
                else QtCore.Qt.AlignmentFlag.AlignLeft
            )
            return horizontal | QtCore.Qt.AlignmentFlag.AlignVCenter
        return None

    def headerData(self, section, orientation, role=QtCore.Qt.ItemDataRole.DisplayRole):
        if role != QtCore.Qt.ItemDataRole.DisplayRole:
            return None
        return (
            self.columns[section]
            if orientation == QtCore.Qt.Orientation.Horizontal
            else str(section + 1)
        )


class _SectionalWorker(QtCore.QObject):
    log = QtCore.Signal(str)
    progress = QtCore.Signal(int, int)
    completed = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(
        self, runner: RunSectionalCasesCallback, rows, definitions, workers
    ) -> None:
        super().__init__()
        self._runner = runner
        self._rows, self._definitions, self._workers = rows, definitions, workers
        self._cancel_event = threading.Event()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            result = self._runner(
                GuiSectionalRunRequest(
                    self._rows,
                    self._definitions,
                    self._workers,
                    self.log.emit,
                    self.progress.emit,
                    self._cancel_event.is_set,
                )
            )
            if not isinstance(result, SectionalBatchResult):
                raise TypeError("sectional adapter must return SectionalBatchResult")
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        # The service owns terminal status and retains cancelled/failed prefixes.
        # Never replace its structured result with an empty cancellation signal.
        self.completed.emit(result)

    def cancel(self) -> None:
        self._cancel_event.set()


class _ExportWorker(QtCore.QObject):
    completed = QtCore.Signal(object)
    failed = QtCore.Signal(str)

    def __init__(self, path, result, protected_paths) -> None:
        super().__init__()
        self._path, self._result, self._protected_paths = path, result, protected_paths

    @QtCore.Slot()
    def run(self) -> None:
        try:
            path = write_sectional_csv(self._path, self._result, self._protected_paths)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.completed.emit(path)


class SectionalLoadsDialog(QtWidgets.QDialog):
    """Persistent modeless workflow; hide/reopen preserves exportable results."""

    run_finished = QtCore.Signal()
    export_failed = QtCore.Signal()

    def __init__(self, spec: SolverSpec, cases_panel: CasesPanel, parent=None) -> None:
        super().__init__(parent)
        if spec.adapters is None or spec.adapters.run_sectional_cases is None:
            raise ValueError("sectional run adapter is required")
        self._runner = spec.adapters.run_sectional_cases
        self.cases_panel = cases_panel
        self.setWindowTitle(f"Sectional Loads — {spec.domain_name}")
        self.setModal(False)
        self.resize(1040, 700)
        self.definition_path: Path | None = None
        self._loaded_definition_paths: tuple[Path, ...] = ()
        self.definitions: tuple[SectionalDefinition, ...] = ()
        self.batch_result: SectionalBatchResult | None = None
        self._protected_paths: tuple[Path, ...] = ()
        self._active_protected_paths: tuple[Path, ...] = ()
        self._run_output_path: Path | None = None
        self._thread: QtCore.QThread | None = None
        self._worker: _SectionalWorker | _ExportWorker | None = None
        self._normal_running = cases_panel.is_running()
        self._close_when_finished = False
        self._cancel_requested = False
        self._operation = ""

        self.path_value = QtWidgets.QLineEdit()
        self.path_value.setReadOnly(True)
        self.path_value.setPlaceholderText("Open sectional definition CSV")
        self.path_value.setAccessibleName("Sectional definition CSV")
        self.btn_open = QtWidgets.QPushButton("Open Definitions...")
        self.btn_reload = QtWidgets.QPushButton("Reload")
        self.definition_status = QtWidgets.QLabel(
            "No definitions loaded. Edit definitions in an external CSV editor."
        )
        self.definition_status.setWordWrap(True)
        self.definition_table = self._table("Sectional definitions")
        self.definition_model = _ReadOnlyModel(self)
        self.definition_table.setModel(self.definition_model)
        self.selection_status = QtWidgets.QLabel()
        self.selection_status.setWordWrap(True)
        self.btn_run = QtWidgets.QPushButton("Run Selected Cases × Sections")
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_export = QtWidgets.QPushButton("Export Results...")
        set_semantic_property(self.btn_run, "fluentAppearance", "primary")
        set_semantic_property(self.btn_cancel, "fluentAppearance", "danger")
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("Idle")
        self.result_status = QtWidgets.QLabel("No computed sectional results.")
        self.result_status.setWordWrap(True)
        self.result_status.setTextInteractionFlags(
            QtCore.Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.result_table = self._table("Sectional results")
        self.result_model = _ReadOnlyModel(self)
        self.result_table.setModel(self.result_model)
        self.btn_close = QtWidgets.QPushButton("Close")
        self.btn_close.setAutoDefault(False)
        for button in (
            self.btn_open,
            self.btn_reload,
            self.btn_run,
            self.btn_cancel,
            self.btn_export,
        ):
            button.setAutoDefault(False)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.path_value)
        file_actions = FlowLayout()
        file_actions.addWidget(self.btn_open)
        file_actions.addWidget(self.btn_reload)
        layout.addLayout(file_actions)
        layout.addWidget(self.definition_status)
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        splitter.addWidget(self.definition_table)
        result_panel = QtWidgets.QWidget()
        result_layout = QtWidgets.QVBoxLayout(result_panel)
        result_layout.setContentsMargins(0, 0, 0, 0)
        result_layout.addWidget(self.result_status)
        result_layout.addWidget(self.result_table)
        splitter.addWidget(result_panel)
        splitter.setSizes([230, 260])
        layout.addWidget(splitter, 1)
        layout.addWidget(self.selection_status)
        actions = FlowLayout()
        for button in (self.btn_run, self.btn_cancel, self.btn_export, self.btn_close):
            actions.addWidget(button)
        layout.addLayout(actions)
        layout.addWidget(self.progress)

        self.btn_open.clicked.connect(self.open_definitions)
        self.btn_reload.clicked.connect(self.reload_definitions)
        self.btn_run.clicked.connect(self.request_run)
        self.btn_cancel.clicked.connect(self.cancel_run)
        self.btn_export.clicked.connect(self.export_results)
        self.btn_close.clicked.connect(self.close)
        self.definition_table.selectionModel().selectionChanged.connect(
            self._refresh_controls
        )
        cases_panel.selected_cases_changed.connect(self._refresh_controls)
        cases_panel.cases_updated.connect(self._refresh_controls)
        cases_panel.run_state_changed.connect(self._normal_state_changed)
        cases_panel.spin_workers.valueChanged.connect(self._refresh_controls)
        self._refresh_controls()

    @staticmethod
    def _table(name: str) -> QtWidgets.QTableView:
        table = QtWidgets.QTableView()
        table.setAccessibleName(name)
        table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        table.setAlternatingRowColors(True)
        table.setWordWrap(False)
        table.verticalHeader().setVisible(False)
        table.setMinimumHeight(100)
        return table

    @staticmethod
    def _ensure_header_widths(table: QtWidgets.QTableView) -> None:
        header = table.horizontalHeader()
        # Match CasesPanel's native-style header minimum; content autosizing
        # alone can leave labels crowded against the section boundaries.
        padding = 2 * table.style().pixelMetric(
            QtWidgets.QStyle.PixelMetric.PM_HeaderMargin, None, header
        )
        for column in range(header.count()):
            table.setColumnWidth(
                column,
                max(
                    table.columnWidth(column), header.sectionSizeHint(column) + padding
                ),
            )

    def _normal_state_changed(self, running: bool) -> None:
        self._normal_running = running
        self._refresh_controls()

    def _refresh_controls(self, *_args) -> None:
        busy = self.is_running()
        selected = bool(self.cases_panel.selected_case_rows())
        cases = len(self.cases_panel.selected_or_all_case_rows())
        sections = len(self.selected_definitions())
        reason = " — ordinary solve running" if self._normal_running else ""
        self.selection_status.setText(
            f"Run scope: {cases} {'selected' if selected else 'all loaded'} case(s) × {sections} selected section(s). "
            f"No case selection runs all cases. Workers: {self.cases_panel.spin_workers.value()}{reason}"
        )
        self.btn_run.setText(
            f"Run {'Selected' if selected else 'All'} Cases × Sections"
        )
        self.btn_open.setEnabled(not busy)
        self.btn_reload.setEnabled(not busy and self.definition_path is not None)
        self.definition_table.setEnabled(not busy)
        self.btn_run.setEnabled(
            not busy and not self._normal_running and cases > 0 and sections > 0
        )
        self.btn_cancel.setEnabled(
            busy and self._operation == "run" and not self._cancel_requested
        )
        self.btn_export.setEnabled(
            not busy
            and not self._normal_running
            and self.batch_result is not None
            and self.batch_result.csv is not None
        )

    def selected_definitions(self) -> tuple[SectionalDefinition, ...]:
        indices = sorted(
            index.row()
            for index in self.definition_table.selectionModel().selectedRows()
        )
        return tuple(self.definitions[index] for index in indices)

    def open_definitions(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open Sectional Definitions",
            str(self.definition_path or Path.cwd()),
            "CSV (*.csv)",
        )
        if path:
            self.load_definitions(path)

    def reload_definitions(self) -> None:
        if self.definition_path is not None:
            self.load_definitions(self.definition_path)

    def load_definitions(self, path: str | Path) -> bool:
        if self.is_running():
            return False
        candidate = Path(path).expanduser().absolute()
        # Invalid reload disables execution instead of displaying new file text
        # while silently retaining the previous numerical definitions.
        self.definition_path = candidate
        self.path_value.setText(str(candidate))
        try:
            resolved_source = candidate.resolve(strict=False)
            definitions = read_sectional_definitions(candidate)
        except Exception as exc:
            self.definitions = ()
            self._loaded_definition_paths = ()
            self.definition_model.replace((), ())
            self.definition_status.setText(f"Definition read failed: {exc}")
            self.cases_panel.logln(f"[ERROR] Sectional definitions: {exc}")
            self._refresh_controls()
            return False
        self.definitions = definitions
        self._loaded_definition_paths = (candidate, resolved_source)
        columns = (
            "section_id",
            "origin STL [m]",
            "direction STL",
            "start [m]",
            "stop [m]",
            "bins",
            "components",
        )
        records = []
        for item in definitions:
            definition = item.definition
            records.append(
                dict(
                    zip(
                        columns,
                        (
                            item.section_id,
                            ", ".join(
                                str(float(value))
                                for value in definition.axis_origin_stl_m
                            ),
                            ", ".join(
                                str(float(value))
                                for value in definition.axis_direction_stl
                            ),
                            "auto"
                            if definition.start_m is None
                            else definition.start_m,
                            "auto" if definition.stop_m is None else definition.stop_m,
                            definition.bin_count,
                            "all"
                            if definition.component_ids is None
                            else ";".join(map(str, definition.component_ids)),
                        ),
                        strict=True,
                    )
                )
            )
        self.definition_model.replace(columns, records)
        self.definition_table.resizeColumnsToContents()
        self._ensure_header_widths(self.definition_table)
        self.definition_status.setText(
            f"Loaded {len(definitions)} read-only definition(s). Select one or more rows; edit the CSV externally and Reload."
        )
        self._refresh_controls()
        return True

    def request_run(self) -> None:
        if (
            self.is_running()
            or self._normal_running
            or self.cases_panel.is_running()
            or not self.cases_panel.case_rows
            or self.cases_panel.input_path is None
            or not self.selected_definitions()
        ):
            return
        default = default_summary_output_path(self.cases_panel.input_path).with_name(
            f"{self.cases_panel.input_path.stem}_sectional_loads.csv"
        )
        try:
            default.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            # A read-only input directory must not prevent choosing another one.
            default = self.cases_panel.input_path.with_name(default.name)
        selected, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save Sectional Results", str(default), "CSV (*.csv)"
        )
        if not selected:
            self.cases_panel.logln("[SKIP] Sectional result output canceled.")
            return
        self.start_run(selected)

    def start_run(self, output_path: str | Path) -> bool:
        if self.is_running() or self._normal_running or self.cases_panel.is_running():
            return False
        rows = tuple(
            MappingProxyType(deepcopy(dict(row)))
            for row in self.cases_panel.selected_or_all_case_rows()
        )
        definitions = self.selected_definitions()
        if (
            not rows
            or not definitions
            or self.cases_panel.input_path is None
            or self.definition_path is None
        ):
            self.selection_status.setText(
                "Load cases and select at least one definition before running."
            )
            return False
        try:
            protected_paths = self._current_protected_paths()
            output = validate_csv_output_path(output_path, protected_paths)
        except Exception as exc:
            self.result_status.setText(f"Invalid output path: {exc}")
            self.cases_panel.logln(f"[ERROR] Sectional output: {exc}")
            return False
        self._active_protected_paths = protected_paths
        self._run_output_path = output
        self._cancel_requested = False
        self.progress.setRange(0, len(rows))
        self.progress.setValue(0)
        self.progress.setFormat(f"Running 0/{len(rows)} cases")
        self.result_status.setText(
            f"Running snapshot: {len(rows)} case(s) × {len(definitions)} section(s). Output: {output}"
        )
        worker = _SectionalWorker(
            self._runner, rows, definitions, int(self.cases_panel.spin_workers.value())
        )
        worker.log.connect(self.cases_panel.logln)
        worker.progress.connect(self._progress)
        worker.completed.connect(self._completed)
        worker.failed.connect(self._failed)
        self._start_worker(worker, "run")
        return True

    def _start_worker(self, worker, operation: str) -> None:
        thread = QtCore.QThread(self)
        self._thread, self._worker, self._operation = thread, worker, operation
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(self._cleanup_worker)
        thread.finished.connect(thread.deleteLater)
        self.cases_panel.set_external_run_active(True)
        set_semantic_property(self.progress, "fluentBusy", True)
        set_semantic_property(self.progress, "fluentStatus", "info")
        self._refresh_controls()
        thread.start()

    def is_running(self) -> bool:
        return self._thread is not None

    def cancel_run(self) -> None:
        if not self.is_running():
            return
        if isinstance(self._worker, _SectionalWorker):
            self._cancel_requested = True
            self._worker.cancel()
            self.progress.setFormat("Cancelling… waiting for a safe boundary")
        else:
            self.progress.setFormat("Saving… waiting for atomic export")
        self._refresh_controls()

    @QtCore.Slot(int, int)
    def _progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        self.progress.setFormat(
            f"{'Cancelling…' if self._cancel_requested else 'Running'} {done}/{total} cases"
        )

    @QtCore.Slot(object)
    def _completed(self, result: SectionalBatchResult) -> None:
        self.batch_result = result
        if result.csv is None:
            self._run_output_path = None
        self._protected_paths = self._active_protected_paths
        self.result_model.replace(
            result.csv.columns if result.csv else (),
            result.csv.rows if result.csv else (),
        )
        for index, column in enumerate(self.result_model.columns):
            self.result_table.setColumnWidth(
                index,
                max(
                    110, self.result_table.fontMetrics().horizontalAdvance(column) + 24
                ),
            )
        self._ensure_header_widths(self.result_table)
        summary = f"{result.status.capitalize()}: {result.completed_pairs}/{result.requested_pairs} case × section pairs; {result.completed_cases}/{result.total_cases} complete cases."
        if result.errors:
            summary += " " + "; ".join(
                f"case {error.case_id!r}, section {error.section_id!r}: {error.message}"
                for error in result.errors[:3]
            )
        self.result_status.setText(summary)
        self.progress.setFormat(result.status.capitalize())
        self.progress.setValue(result.completed_cases)
        set_semantic_property(
            self.progress,
            "fluentStatus",
            "success"
            if result.status == "completed"
            else "warning"
            if result.status == "cancelled"
            else "danger",
        )
        self.cases_panel.logln(f"[SECTIONAL] {summary}")

    @QtCore.Slot(str)
    def _failed(self, message: str) -> None:
        # An exception must never auto-save an earlier run's retained result.
        self._run_output_path = None
        self.result_status.setText(
            f"Calculation failed: {message}. Previous computed results, if any, are retained for export."
        )
        self.progress.setFormat("Failed")
        set_semantic_property(self.progress, "fluentStatus", "danger")
        self.cases_panel.logln(f"[ERROR] Sectional calculation: {message}")

    def export_results(self, path: str | Path | None = None) -> bool:
        if (
            self.is_running()
            or self._normal_running
            or self.cases_panel.is_running()
            or self.batch_result is None
            or self.batch_result.csv is None
        ):
            return False
        # clicked(bool) is not a destination argument.
        if isinstance(path, bool):
            path = None
        if path is None:
            selected, _ = QtWidgets.QFileDialog.getSaveFileName(
                self,
                "Export Sectional Results",
                "sectional_loads_result.csv",
                "CSV (*.csv)",
            )
            if not selected:
                return False
            path = selected
        try:
            protected = tuple(
                dict.fromkeys(
                    (*self._protected_paths, *self._current_protected_paths())
                )
            )
        except Exception as exc:
            self._export_failed(str(exc))
            return False
        worker = _ExportWorker(Path(path), self.batch_result, protected)
        worker.completed.connect(self._exported)
        worker.failed.connect(self._export_failed)
        self.progress.setFormat("Saving…")
        self._start_worker(worker, "export")
        return True

    def _current_protected_paths(self) -> tuple[Path, ...]:
        current = (
            sectional_protected_paths(
                self.cases_panel.input_path,
                self.definition_path,
                self.cases_panel.case_rows,
            )
            if self.cases_panel.input_path is not None
            and self.definition_path is not None
            else ()
        )
        return tuple(
            dict.fromkeys(
                (
                    *self._loaded_definition_paths,
                    *self.cases_panel._loaded_input_paths,
                    *current,
                )
            )
        )

    @QtCore.Slot(object)
    def _exported(self, path: Path) -> None:
        assert self.batch_result is not None
        self.result_status.setText(
            f"Exported {self.batch_result.status} snapshot ({self.batch_result.completed_pairs}/{self.batch_result.requested_pairs} pairs): {path}"
        )
        self.progress.setFormat(f"Exported ({self.batch_result.status})")
        set_semantic_property(
            self.progress,
            "fluentStatus",
            "success" if self.batch_result.status == "completed" else "warning",
        )

    @QtCore.Slot(str)
    def _export_failed(self, message: str) -> None:
        self._close_when_finished = False
        self.result_status.setText(
            f"Export failed: {message}. Computed results are retained; choose Export Results to retry."
        )
        self.progress.setFormat("Export failed")
        set_semantic_property(self.progress, "fluentStatus", "danger")
        self.cases_panel.logln(f"[ERROR] Sectional export: {message}")
        self.export_failed.emit()

    @QtCore.Slot()
    def _cleanup_worker(self) -> None:
        self._thread = None
        self._worker = None
        self._operation = ""
        self._active_protected_paths = ()
        output, self._run_output_path = self._run_output_path, None
        # Keep the run guard and close request across calculation -> export.
        # run_finished is emitted only after the final writer is cleaned up.
        if output is not None and self.export_results(output):
            return
        self.cases_panel.set_external_run_active(False)
        set_semantic_property(self.progress, "fluentBusy", False)
        self._refresh_controls()
        self.run_finished.emit()
        if self._close_when_finished:
            self._close_when_finished = False
            QtCore.QTimer.singleShot(0, self.close)

    def closeEvent(self, event) -> None:
        if self.is_running():
            self._close_when_finished = True
            self.cancel_run()
            event.ignore()
            return
        super().closeEvent(event)

    def reject(self) -> None:
        # QDialog's Escape route otherwise bypasses closeEvent.
        if self.is_running():
            self._close_when_finished = True
            self.cancel_run()
            return
        super().reject()


__all__ = ("SectionalLoadsDialog",)
