"""Shared case loading, table selection, and automatic artifact matching."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path

import pyvista as pv
from PySide6 import QtCore, QtWidgets

from .path_resolution import (
    absolute_input_path,
    default_summary_output_path,
    resolve_case_vtp_path,
)
from .run_lifecycle import CaseRunWorker
from .runtime import DEFAULT_CHECKPOINT_CASES
from .solver_spec import CaseRow, GuiRunResult, SolverSpec
from .viewer_data import match_artifact_case


def _issue_value(issue: object, name: str) -> object | None:
    if isinstance(issue, Mapping):
        return issue.get(name)
    return getattr(issue, name, None)


class ValidationIssuesDialog(QtWidgets.QDialog):
    """Product-neutral tabular rendering of structured validation issues."""

    def __init__(self, file_path: str, issues: Sequence[object], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Input Validation Errors")
        self.resize(980, 420)
        self._issues = tuple(issues)
        layout = QtWidgets.QVBoxLayout(self)
        summary = QtWidgets.QLabel(
            f"Failed to load input file:\n{file_path}\n\n"
            f"Validation issues: {len(self._issues)}"
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)
        self.table = QtWidgets.QTableWidget(len(self._issues), 4)
        self.table.setHorizontalHeaderLabels(["Row", "Case ID", "Field", "Message"])
        self.table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        for row_index, issue in enumerate(self._issues):
            values = (
                _issue_value(issue, "row_number"),
                _issue_value(issue, "case_id"),
                _issue_value(issue, "field"),
                _issue_value(issue, "message"),
            )
            for column, value in enumerate(values):
                text = "" if value is None else str(value)
                self.table.setItem(row_index, column, QtWidgets.QTableWidgetItem(text))
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table, 1)
        buttons = QtWidgets.QHBoxLayout()
        buttons.addStretch(1)
        copy_button = QtWidgets.QPushButton("Copy")
        close_button = QtWidgets.QPushButton("Close")
        buttons.addWidget(copy_button)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)
        copy_button.clicked.connect(self.copy_issues)
        close_button.clicked.connect(self.accept)

    def copy_issues(self) -> None:
        lines = ["row\tcase_id\tfield\tmessage"]
        for issue in self._issues:
            values = (
                _issue_value(issue, "row_number"),
                _issue_value(issue, "case_id"),
                _issue_value(issue, "field"),
                _issue_value(issue, "message"),
            )
            lines.append("\t".join("" if value is None else str(value) for value in values))
        QtWidgets.QApplication.clipboard().setText("\n".join(lines))


class CasesPanel(QtWidgets.QWidget):
    """Load product-adapted rows and coordinate selection with the viewer."""

    vtp_loaded = QtCore.Signal(str, object, object)
    viewer_clear_requested = QtCore.Signal()
    cases_updated = QtCore.Signal(object)
    selected_cases_changed = QtCore.Signal(object)
    input_path_changed = QtCore.Signal(object)
    run_requested = QtCore.Signal(object, int, int, object)
    run_finished = QtCore.Signal()

    def __init__(
        self,
        spec: SolverSpec,
        parent=None,
        *,
        artifact_reader=pv.read,
    ) -> None:
        if not isinstance(spec, SolverSpec):
            raise TypeError("spec must be a SolverSpec")
        if spec.adapters is None:
            raise ValueError("spec.adapters is required by CasesPanel")
        if not callable(artifact_reader):
            raise TypeError("artifact_reader must be callable")
        super().__init__(parent)
        self.spec = spec
        self._artifact_reader = artifact_reader
        self._last_input_directory: Path | None = None
        self.case_rows: tuple[CaseRow, ...] = ()
        self.input_path: Path | None = None
        self._table_columns: tuple[str, ...] = ()

        self.input_value = QtWidgets.QLineEdit()
        self.input_value.setReadOnly(True)
        self.input_value.setPlaceholderText("CSV / XLSX / XLSM input file")
        self.btn_pick_input = QtWidgets.QPushButton("Select Input File")
        self.btn_run = QtWidgets.QPushButton("Run Selected Cases")
        self.btn_cancel = QtWidgets.QPushButton("Cancel")
        self.btn_cancel.setEnabled(False)
        self.btn_run.setEnabled(False)
        self.lbl_case_summary = QtWidgets.QLabel("No cases loaded")
        self.lbl_selection_summary = QtWidgets.QLabel("Selected: 0")
        self.spin_workers = QtWidgets.QSpinBox()
        self.spin_workers.setRange(1, os.cpu_count() or 1)
        self.spin_workers.setValue(1)
        self.spin_checkpoint_every_cases = QtWidgets.QSpinBox()
        self.spin_checkpoint_every_cases.setRange(0, 2_147_483_647)
        self.spin_checkpoint_every_cases.setValue(DEFAULT_CHECKPOINT_CASES)
        self.spin_checkpoint_every_cases.setSuffix(" cases")
        self.case_table = QtWidgets.QTableWidget()
        self.case_table.setSelectionMode(
            QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.case_table.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.case_table.setEditTriggers(
            QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.case_table.setAlternatingRowColors(True)
        self.case_table.setWordWrap(False)
        self.case_table.verticalHeader().setVisible(False)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(8000)
        self.log.setMinimumHeight(180)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("Idle")
        self._run_thread: QtCore.QThread | None = None
        self._run_worker: CaseRunWorker | None = None
        self._run_rows: tuple[CaseRow, ...] = ()
        self._run_output_path: Path | None = None
        self._build_layout()

        self.btn_pick_input.clicked.connect(self.pick_input_file)
        self.btn_run.clicked.connect(self.request_run)
        self.btn_cancel.clicked.connect(self.cancel_run)
        self.case_table.itemSelectionChanged.connect(self.on_case_selection_changed)
        self.run_requested.connect(self.start_run)

    def _build_layout(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        input_row = QtWidgets.QHBoxLayout()
        input_row.addWidget(self.input_value, 1)
        input_row.addWidget(self.btn_pick_input)
        layout.addLayout(input_row)
        summaries = QtWidgets.QHBoxLayout()
        summaries.addWidget(self.lbl_case_summary)
        summaries.addStretch(1)
        summaries.addWidget(self.lbl_selection_summary)
        layout.addLayout(summaries)
        layout.addWidget(self.case_table, 4)
        run_row = QtWidgets.QHBoxLayout()
        run_row.addWidget(QtWidgets.QLabel("Workers:"))
        run_row.addWidget(self.spin_workers)
        run_row.addWidget(QtWidgets.QLabel("Checkpoint every:"))
        run_row.addWidget(self.spin_checkpoint_every_cases)
        run_row.addStretch(1)
        run_row.addWidget(self.btn_run)
        run_row.addWidget(self.btn_cancel)
        layout.addLayout(run_row)
        layout.addWidget(self.progress)
        layout.addWidget(self.log, 2)

    def logln(self, message: str) -> None:
        self.log.appendPlainText(message)

    def input_dialog_directory(self) -> Path:
        """Return this session's existing input directory, or the current one."""
        candidate = self._last_input_directory
        if candidate is not None and candidate.is_dir():
            return candidate
        return Path.cwd()

    def pick_input_file(self) -> None:
        """Open the shared normal-input picker used by both GUI entry points."""
        if self.is_running():
            self.logln("[WARN] Cannot open another input while cases are running.")
            return
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Select Input File",
            str(self.input_dialog_directory()),
            "CSV/Excel (*.csv *.xlsx *.xlsm)",
        )
        if path:
            self.load_input_file(path)

    def load_input_file(
        self,
        path: str | Path,
        *,
        remember_directory: bool = True,
    ) -> bool:
        """Read cases through the selected product adapter and reset on failure."""
        try:
            raw_rows = self.spec.adapters.read_cases(path)
            rows = tuple(raw_rows)
            if not rows:
                raise ValueError("Input contains no cases.")
            if any(not isinstance(row, Mapping) for row in rows):
                raise TypeError("read_cases must return mappings")
            normalized = tuple(dict(row) for row in rows)
        except Exception as exc:
            self.clear_loaded_cases()
            issues = getattr(exc, "issues", None)
            if issues is not None:
                issue_list = tuple(issues)
                self.logln(f"[ERROR] Invalid input file: {len(issue_list)} issue(s).")
                ValidationIssuesDialog(str(path), issue_list, self).exec()
            else:
                self.logln(f"[ERROR] Failed to read input file: {exc}")
                QtWidgets.QMessageBox.critical(
                    self,
                    "Input Read Error",
                    f"Failed to read input file:\n{path}\n\n{exc}",
                )
            return False

        self.input_path = absolute_input_path(path)
        self.input_value.setText(str(self.input_path))
        self.case_rows = normalized
        self._populate_case_table()
        self.btn_run.setEnabled(True)
        if remember_directory:
            self._last_input_directory = self.input_path.parent
        self.logln(f"[OK] Loaded {len(self.case_rows)} case(s). Select and run.")
        self.input_path_changed.emit(self.input_path)
        self.cases_updated.emit(self.case_rows)
        self.selected_cases_changed.emit(())
        return True

    def _ordered_columns(self) -> tuple[str, ...]:
        extras: list[str] = []
        known = set(self.spec.case_columns)
        for row in self.case_rows:
            for name in row:
                if name not in known and name not in extras:
                    extras.append(name)
        return (*self.spec.case_columns, *extras)

    def _populate_case_table(self) -> None:
        self._table_columns = self._ordered_columns()
        self.case_table.clear()
        self.case_table.setColumnCount(len(self._table_columns))
        self.case_table.setRowCount(len(self.case_rows))
        headers = [
            "stl_name" if name == "stl_path" else name
            for name in self._table_columns
        ]
        self.case_table.setHorizontalHeaderLabels(headers)
        for row_index, row in enumerate(self.case_rows):
            for column, name in enumerate(self._table_columns):
                value = row.get(name)
                text = "" if value is None else str(value)
                display = self.format_stl_name(text) if name == "stl_path" else text
                item = QtWidgets.QTableWidgetItem(display)
                if name == "stl_path" and text:
                    item.setToolTip(text)
                if column == 0:
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, row_index)
                self.case_table.setItem(row_index, column, item)
        self.case_table.resizeColumnsToContents()
        if "stl_path" in self._table_columns:
            self.case_table.setColumnWidth(self._table_columns.index("stl_path"), 220)
        self._refresh_summary()

    @staticmethod
    def format_stl_name(value: str) -> str:
        paths = [part.strip() for part in value.split(";") if part.strip()]
        return ", ".join(Path(path).name for path in paths)

    def selected_case_rows(self) -> list[CaseRow]:
        selection = self.case_table.selectionModel().selectedRows()
        indices = sorted(
            {
                int(item.data(QtCore.Qt.ItemDataRole.UserRole))
                for model_index in selection
                if (item := self.case_table.item(model_index.row(), 0)) is not None
                and item.data(QtCore.Qt.ItemDataRole.UserRole) is not None
            }
        )
        return [self.case_rows[index] for index in indices]

    def selected_or_all_case_rows(self) -> list[CaseRow]:
        selected = self.selected_case_rows()
        return selected if selected else list(self.case_rows)

    def on_case_selection_changed(self) -> None:
        self._refresh_summary()
        selected = self.selected_case_rows()
        self.selected_cases_changed.emit(tuple(selected))
        if not selected:
            self.viewer_clear_requested.emit()
            return
        self._auto_load_case_artifact(selected[0])

    def _auto_load_case_artifact(self, row: CaseRow) -> None:
        case_id = str(row.get("case_id", "")).strip()
        if not case_id:
            self.viewer_clear_requested.emit()
            return
        if self.input_path is None:
            self.viewer_clear_requested.emit()
            return
        path = resolve_case_vtp_path(row, self.input_path)
        if not path.exists():
            self.viewer_clear_requested.emit()
            return
        try:
            artifact = self._artifact_reader(str(path))
        except Exception as exc:
            self.viewer_clear_requested.emit()
            self.logln(f"[ERROR] Failed to read VTP: {exc}")
            return
        candidates = self.spec.adapters.build_case_signatures(row)
        if match_artifact_case(artifact, row, candidates).matched:
            self.vtp_loaded.emit(str(path), artifact, row)
        else:
            self.viewer_clear_requested.emit()

    def request_run(self) -> None:
        if self.input_path is None or not self.case_rows:
            return
        rows = self.selected_or_all_case_rows()
        default_path = default_summary_output_path(self.input_path)
        output_dir = default_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        selected_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save Results",
            str(default_path),
            "CSV (*.csv)",
        )
        if not selected_path:
            self.logln("[SKIP] Result output canceled.")
            return
        try:
            output_path = self.spec.adapters.validate_output_path(
                selected_path,
                self.input_path,
                rows,
            )
        except Exception as exc:
            self.logln(f"[ERROR] {exc}")
            QtWidgets.QMessageBox.critical(
                self,
                "Invalid Output Path",
                str(exc),
            )
            return
        self.run_requested.emit(
            rows,
            int(self.spin_workers.value()),
            int(self.spin_checkpoint_every_cases.value()),
            output_path,
        )

    @QtCore.Slot(object, int, int, object)
    def start_run(
        self,
        rows: Sequence[CaseRow],
        workers: int,
        checkpoint_every_cases: int,
        output_path: str | Path,
    ) -> bool:
        """Start exactly one background adapter run."""
        if self._run_thread is not None:
            self.logln("[WARN] A case run is already active.")
            return False
        selected = tuple(dict(row) for row in rows)
        if not selected:
            self.logln("[WARN] No cases are available to run.")
            return False
        self._run_rows = selected
        self._run_output_path = Path(output_path)
        total = len(selected)
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self.progress.setFormat(f"0/{total}")
        self._set_running_state(True)
        self.logln(f"[RUN] Running {total} case(s)...")

        thread = QtCore.QThread(self)
        worker = CaseRunWorker(
            self.spec.adapters.run_cases,
            selected,
            workers,
            checkpoint_every_cases,
            self._run_output_path,
        )
        self._run_thread = thread
        self._run_worker = worker
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.log.connect(self.logln)
        worker.progress.connect(self._on_run_progress)
        worker.completed.connect(self._on_run_completed)
        worker.failed.connect(self._on_run_failed)
        worker.canceled.connect(self._on_run_canceled)
        worker.completed.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.canceled.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        worker.canceled.connect(worker.deleteLater)
        thread.finished.connect(self._cleanup_run_worker)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        return True

    def cancel_run(self) -> None:
        """Request cooperative cancellation at the next scheduler boundary."""
        if self._run_worker is None:
            return
        self._run_worker.cancel()
        self.btn_cancel.setEnabled(False)
        self.logln("[CANCEL] Cancellation requested...")

    def is_running(self) -> bool:
        return self._run_thread is not None

    @QtCore.Slot(int, int)
    def _on_run_progress(self, done: int, total: int) -> None:
        safe_total = max(int(total), 1)
        safe_done = min(max(int(done), 0), safe_total)
        self.progress.setRange(0, safe_total)
        self.progress.setValue(safe_done)
        self.progress.setFormat(f"{done}/{total}")

    @QtCore.Slot(object)
    def _on_run_completed(self, result: GuiRunResult) -> None:
        total = len(self._run_rows)
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(total)
        self.progress.setFormat(f"{total}/{total}")
        if self._run_output_path is not None:
            self.logln(f"[OK] Wrote results: {self._run_output_path}")
        self._refresh_first_result(result)

    def _refresh_first_result(self, result: GuiRunResult) -> None:
        if result.first_vtp_path is None:
            return
        row = (
            result.first_case_row
            if result.first_case_row is not None
            else (self._run_rows[0] if self._run_rows else None)
        )
        if row is None:
            self.viewer_clear_requested.emit()
            return
        path = result.first_vtp_path
        try:
            artifact = self._artifact_reader(str(path))
        except Exception as exc:
            self.viewer_clear_requested.emit()
            self.logln(f"[ERROR] Failed to read VTP: {exc}")
            return
        candidates = self.spec.adapters.build_case_signatures(row)
        if match_artifact_case(artifact, row, candidates).matched:
            self.vtp_loaded.emit(str(path), artifact, row)
        else:
            self.viewer_clear_requested.emit()

    @QtCore.Slot(str)
    def _on_run_failed(self, message: str) -> None:
        self.logln(f"[ERROR] {message}")
        self.progress.setFormat("Failed")

    @QtCore.Slot()
    def _on_run_canceled(self) -> None:
        self.logln("[CANCEL] Run canceled.")
        self.progress.setFormat("Canceled")

    @QtCore.Slot()
    def _cleanup_run_worker(self) -> None:
        self._run_worker = None
        self._run_thread = None
        self._run_rows = ()
        self._run_output_path = None
        self._set_running_state(False)
        self.run_finished.emit()

    def _set_running_state(self, running: bool) -> None:
        self.btn_pick_input.setEnabled(not running)
        self.spin_workers.setEnabled(not running)
        self.case_table.setEnabled(not running)
        self.btn_cancel.setEnabled(running)
        self.btn_run.setEnabled((not running) and bool(self.case_rows))

    def clear_loaded_cases(self) -> None:
        self.case_rows = ()
        self.input_path = None
        self._table_columns = ()
        self.input_value.clear()
        self.case_table.clear()
        self.case_table.setRowCount(0)
        self.case_table.setColumnCount(0)
        self.btn_run.setEnabled(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("Idle")
        self.viewer_clear_requested.emit()
        self.input_path_changed.emit(None)
        self.cases_updated.emit(self.case_rows)
        self.selected_cases_changed.emit(())
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        total = len(self.case_rows)
        selected = len(self.case_table.selectionModel().selectedRows())
        self.lbl_case_summary.setText(
            "No cases loaded" if total == 0 else f"Loaded: {total} case(s)"
        )
        self.lbl_selection_summary.setText(f"Selected: {selected}")


__all__ = ("CasesPanel", "ValidationIssuesDialog")
