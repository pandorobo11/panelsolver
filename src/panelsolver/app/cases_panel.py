"""Shared case loading, table selection, and automatic artifact matching."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import pyvista as pv
from PySide6 import QtCore, QtWidgets

from .gui_components import FlowLayout, FrozenCaseTable, WorkbenchSpinBox
from .gui_theme import set_semantic_property
from .output_status import OutputKind, OutputPhase
from .path_resolution import (
    absolute_input_path,
    default_summary_output_path,
    resolve_case_vtp_path,
)
from .run_lifecycle import CaseRunWorker
from .runtime import DEFAULT_CHECKPOINT_CASES
from .solver_spec import (
    CaseColumnKind,
    CaseColumnWidthRole,
    CaseRow,
    GuiRunResult,
    SolverSpec,
)
from .viewer_data import (
    ArtifactViewState,
    ArtifactViewStatus,
    automatic_artifact_view_state,
)

_INLINE_LABEL_CONTROL_SPACING = 4
_RUN_SETTINGS_GROUP_SPACING = 12
_RUN_ACTION_SPACING = 8


@dataclass(frozen=True, slots=True)
class _ColumnWidthPolicy:
    minimum_text: str
    representative_text: str
    maximum_text: str


_COLUMN_WIDTH_POLICIES = {
    CaseColumnWidthRole.IDENTIFIER: _ColumnWidthPolicy(
        "case_000",
        "case_identifier_000",
        "case_identifier_000000",
    ),
    CaseColumnWidthRole.PATH: _ColumnWidthPolicy(
        "outputs/result",
        "outputs/analysis-results",
        "outputs/engineering-results/archive",
    ),
    CaseColumnWidthRole.COMPACT_NUMERIC: _ColumnWidthPolicy(
        "-0.0",
        "-1.234e+03",
        "-1.234567890e+123",
    ),
    CaseColumnWidthRole.ENGINEERING_NUMERIC: _ColumnWidthPolicy(
        "-0.000000",
        "-1.2345e+12",
        "-1.234567890123456e+12345",
    ),
    CaseColumnWidthRole.MODEL_TEXT: _ColumnWidthPolicy(
        "newtonian",
        "modified_newtonian",
        "unexpected_model_selector",
    ),
    CaseColumnWidthRole.ENUM_TEXT: _ColumnWidthPolicy(
        "auto",
        "beta_sin",
        "unexpected_enum_value",
    ),
    CaseColumnWidthRole.FLAG: _ColumnWidthPolicy(
        "0",
        "1",
        "Boolean flag",
    ),
    CaseColumnWidthRole.FALLBACK: _ColumnWidthPolicy(
        "value",
        "sample value",
        "unexpected extra value",
    ),
}

_FULL_VALUE_TOOLTIP_ROLES = frozenset(
    {
        CaseColumnWidthRole.IDENTIFIER,
        CaseColumnWidthRole.PATH,
        CaseColumnWidthRole.MODEL_TEXT,
        CaseColumnWidthRole.ENUM_TEXT,
        CaseColumnWidthRole.FALLBACK,
    }
)


def _bounded_spin_box_width(spin_box: QtWidgets.QSpinBox, digits: int) -> int:
    """Fit the requested digit count without reserving the full integer range."""
    spin_box.ensurePolished()
    option = QtWidgets.QStyleOptionSpinBox()
    spin_box.initStyleOption(option)
    natural_size = spin_box.sizeHint()
    option.rect = QtCore.QRect(QtCore.QPoint(), natural_size)
    edit_field = spin_box.style().subControlRect(
        QtWidgets.QStyle.ComplexControl.CC_SpinBox,
        option,
        QtWidgets.QStyle.SubControl.SC_SpinBoxEditField,
        spin_box,
    )
    native_chrome_width = max(natural_size.width() - edit_field.width(), 0)
    focus_margin = spin_box.style().pixelMetric(
        QtWidgets.QStyle.PixelMetric.PM_FocusFrameHMargin,
        option,
        spin_box,
    )
    metrics = spin_box.fontMetrics()
    representative_width = max(
        metrics.horizontalAdvance(digit * digits) for digit in "0123456789"
    )
    return native_chrome_width + representative_width + 2 * focus_margin


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
            lines.append(
                "\t".join("" if value is None else str(value) for value in values)
            )
        QtWidgets.QApplication.clipboard().setText("\n".join(lines))


class CasesPanel(QtWidgets.QWidget):
    """Load product-adapted rows and coordinate selection with the viewer."""

    vtp_loaded = QtCore.Signal(str, object, object)
    vtp_artifact_invalidated = QtCore.Signal(str)
    viewer_clear_requested = QtCore.Signal()
    viewer_artifact_state_changed = QtCore.Signal(object)
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
        set_semantic_property(self.btn_pick_input, "fluentAppearance", "secondary")
        set_semantic_property(self.btn_run, "fluentAppearance", "primary")
        set_semantic_property(self.btn_cancel, "fluentAppearance", "danger")
        # Reserve the longest native size hint so scope wording does not move layout.
        self.btn_run.setMinimumWidth(self.btn_run.sizeHint().width())
        self.btn_run.setText("Run Cases")
        self.btn_cancel.setEnabled(False)
        self.btn_run.setEnabled(False)
        self.lbl_case_summary = QtWidgets.QLabel("No cases loaded")
        self.spin_workers = WorkbenchSpinBox()
        self.spin_workers.setAccessibleName("Workers")
        self.spin_workers.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.spin_workers.setRange(1, os.cpu_count() or 1)
        self.spin_workers.setValue(1)
        self.spin_workers.setMaximumWidth(_bounded_spin_box_width(self.spin_workers, 3))
        self.spin_checkpoint_every_cases = WorkbenchSpinBox()
        self.spin_checkpoint_every_cases.setAlignment(
            QtCore.Qt.AlignmentFlag.AlignRight
        )
        self.spin_checkpoint_every_cases.setRange(0, 2_147_483_647)
        self.spin_checkpoint_every_cases.setValue(DEFAULT_CHECKPOINT_CASES)
        self.spin_checkpoint_every_cases.setAccessibleName("Checkpoint every")
        self.spin_checkpoint_every_cases.setAccessibleDescription(
            "Checkpoint interval in cases. Range 0 to 2147483647 cases."
        )
        self.spin_checkpoint_every_cases.setToolTip(
            "Checkpoint interval in cases (0 to 2,147,483,647)."
        )
        self.spin_checkpoint_every_cases.setMaximumWidth(
            _bounded_spin_box_width(self.spin_checkpoint_every_cases, 6)
        )
        self.case_table = FrozenCaseTable()
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
        self.btn_diagnostics = QtWidgets.QPushButton("Show diagnostics")
        self.btn_diagnostics.setCheckable(True)
        self.btn_diagnostics.setAccessibleName("Diagnostics")
        self.btn_clear_diagnostics = QtWidgets.QPushButton("Clear log")
        self.btn_clear_diagnostics.setAccessibleName("Clear diagnostics")
        self.btn_clear_diagnostics.setToolTip(
            "Clear the log and reset warning and error counts"
        )
        self.btn_clear_diagnostics.clicked.connect(self.clear_diagnostics)
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(8000)
        self.log.setMinimumHeight(180)
        self.progress = QtWidgets.QProgressBar()
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.progress.setFormat("Idle")
        set_semantic_property(self.progress, "fluentStatus", "neutral")
        set_semantic_property(self.progress, "fluentBusy", False)
        self._run_thread: QtCore.QThread | None = None
        self._run_worker: CaseRunWorker | None = None
        self._run_rows: tuple[CaseRow, ...] = ()
        self._run_output_path: Path | None = None
        self._invalid_current_vtp_artifacts: set[tuple[str, Path]] = set()
        self._cancel_requested = False
        self._warning_messages = 0
        self._error_messages = 0
        self._column_preferences: dict[str, dict] = {}
        self.btn_clear_selection = QtWidgets.QPushButton("Clear selection")
        self.btn_clear_selection.setToolTip("Clear selection to run all loaded cases")
        self.btn_clear_selection.clicked.connect(self.case_table.clearSelection)
        self.lbl_run_scope = QtWidgets.QLabel("Load an input file to begin")
        self.lbl_run_scope.setWordWrap(True)
        self._build_layout()
        self._set_diagnostics_expanded(False)

        self.btn_pick_input.clicked.connect(self.pick_input_file)
        self.btn_run.clicked.connect(self.request_run)
        self.btn_cancel.clicked.connect(self.cancel_run)
        self.btn_diagnostics.toggled.connect(self._set_diagnostics_expanded)
        self.case_table.itemSelectionChanged.connect(self.on_case_selection_changed)
        self.run_requested.connect(self.start_run)

    def _build_layout(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(8)
        input_row = QtWidgets.QHBoxLayout()
        input_row.addWidget(self.input_value, 1)
        input_row.addWidget(self.btn_pick_input)
        layout.addLayout(input_row)
        summaries = FlowLayout()
        self.lbl_case_summary.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Preferred,
        )
        summaries.addWidget(self.lbl_case_summary)
        summaries.addWidget(self.btn_clear_selection)
        layout.addLayout(summaries)
        layout.addWidget(self.case_table, 4)
        layout.addWidget(self.lbl_run_scope)
        self.lbl_workers = QtWidgets.QLabel("Workers")
        self.lbl_checkpoint_every_cases = QtWidgets.QLabel("Checkpoint")
        self.lbl_checkpoint_unit = QtWidgets.QLabel("cases")
        self.lbl_workers.setBuddy(self.spin_workers)
        self.lbl_checkpoint_every_cases.setBuddy(self.spin_checkpoint_every_cases)

        self.workers_group = QtWidgets.QHBoxLayout()
        self.workers_group.setContentsMargins(0, 0, 0, 0)
        self.workers_group.setSpacing(_INLINE_LABEL_CONTROL_SPACING)
        self.workers_group.addWidget(self.lbl_workers)
        self.workers_group.addWidget(self.spin_workers)

        self.checkpoint_group = QtWidgets.QHBoxLayout()
        self.checkpoint_group.setContentsMargins(0, 0, 0, 0)
        self.checkpoint_group.setSpacing(_INLINE_LABEL_CONTROL_SPACING)
        self.checkpoint_group.addWidget(self.lbl_checkpoint_every_cases)
        self.checkpoint_group.addWidget(self.spin_checkpoint_every_cases)
        self.checkpoint_group.addWidget(self.lbl_checkpoint_unit)

        self.run_actions_group = QtWidgets.QHBoxLayout()
        self.run_actions_group.setContentsMargins(0, 0, 0, 0)
        self.run_actions_group.setSpacing(_RUN_ACTION_SPACING)
        self.run_actions_group.addWidget(self.btn_run)
        self.run_actions_group.addWidget(self.btn_cancel)

        self.settings_row = FlowLayout(spacing=_RUN_SETTINGS_GROUP_SPACING)
        self.settings_row.addLayout(self.workers_group)
        self.settings_row.addLayout(self.checkpoint_group)
        layout.addLayout(self.settings_row)

        self.execution_row = FlowLayout(spacing=_RUN_ACTION_SPACING)
        self.execution_row.addWidget(self.progress)
        self.execution_row.addLayout(self.run_actions_group)
        layout.addLayout(self.execution_row)
        self.diagnostics_row = QtWidgets.QWidget()
        diagnostics = FlowLayout(self.diagnostics_row, spacing=8)
        diagnostics.addWidget(self.btn_diagnostics)
        diagnostics.addWidget(self.btn_clear_diagnostics)
        layout.addWidget(self.diagnostics_row)
        layout.addWidget(self.log, 2)

    def logln(self, message: str) -> None:
        self.log.appendPlainText(message)
        self._warning_messages += int(message.startswith("[WARN]"))
        self._error_messages += int(message.startswith("[ERROR]"))
        self._refresh_diagnostics_label()

    def _refresh_diagnostics_label(self) -> None:
        action = "Hide" if self.btn_diagnostics.isChecked() else "Show"
        text = f"{action} diagnostics"
        if self._warning_messages or self._error_messages:
            text += (
                f" · {self._warning_messages} warnings · {self._error_messages} errors"
            )
        self.btn_diagnostics.setText(text)
        self.btn_clear_diagnostics.setEnabled(not self.log.document().isEmpty())

    @QtCore.Slot()
    def clear_diagnostics(self) -> None:
        self.log.clear()
        self._warning_messages = 0
        self._error_messages = 0
        self._refresh_diagnostics_label()

    def show_diagnostics(self) -> None:
        self.btn_diagnostics.setChecked(True)
        self.log.setFocus()

    @QtCore.Slot(bool)
    def _set_diagnostics_expanded(self, expanded: bool) -> None:
        self.log.setVisible(expanded)
        self._refresh_diagnostics_label()
        description = "Hide diagnostic log" if expanded else "Show diagnostic log"
        self.btn_diagnostics.setToolTip(description)
        self.btn_diagnostics.setAccessibleDescription(description)

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
        self._invalid_current_vtp_artifacts.clear()
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
        if self._table_columns:
            self._column_preferences = self.column_preferences()
        self._table_columns = self._ordered_columns()
        self.case_table.clear()
        self.case_table.setColumnCount(len(self._table_columns))
        self.case_table.setRowCount(len(self.case_rows))
        presentations = {
            presentation.name: presentation
            for presentation in self.spec.case_column_presentations
        }
        headers = [
            presentations[name].label.replace(" [", "\n[", 1)
            if name in presentations
            else name
            for name in self._table_columns
        ]
        self.case_table.setHorizontalHeaderLabels(headers)
        for column, name in enumerate(self._table_columns):
            if name in presentations:
                self.case_table.horizontalHeaderItem(column).setToolTip(
                    presentations[name].label
                )
        width_roles = [
            (
                presentations[name].width_role
                if name in presentations
                else CaseColumnWidthRole.FALLBACK
            )
            for name in self._table_columns
        ]
        column_widths = [
            self._initial_column_width(column, role)
            for column, role in enumerate(width_roles)
        ]
        for column, width in enumerate(column_widths):
            self.case_table.setColumnWidth(column, width)
            if (
                self._header_width(column) > width
                and not self.case_table.horizontalHeaderItem(column).toolTip()
            ):
                header_item = self.case_table.horizontalHeaderItem(column)
                header_item.setToolTip(header_item.text())
        for row_index, row in enumerate(self.case_rows):
            for column, name in enumerate(self._table_columns):
                value = row.get(name)
                text = "" if value is None else str(value)
                display = self.format_stl_name(text) if name == "stl_path" else text
                item = QtWidgets.QTableWidgetItem(display)
                kind = (
                    presentations[name].kind
                    if name in presentations
                    else CaseColumnKind.TEXT
                )
                item.setTextAlignment(self._column_alignment(kind))
                if name == "stl_path" and text:
                    item.setToolTip(text)
                elif (
                    display
                    and width_roles[column] in _FULL_VALUE_TOOLTIP_ROLES
                    and self._needs_full_value_tooltip(
                        display,
                        column_widths[column],
                    )
                ):
                    item.setToolTip(display)
                if column == 0:
                    item.setData(QtCore.Qt.ItemDataRole.UserRole, row_index)
                self.case_table.setItem(row_index, column, item)
        self.restore_columns(self._column_preferences)
        self.case_table.refresh_frozen()
        self._refresh_summary()

    def column_preferences(self) -> dict[str, dict]:
        return {
            name: {"width": self.case_table.columnWidth(column)}
            for column, name in enumerate(self._table_columns)
        }

    def restore_columns(self, preferences: dict) -> None:
        self._column_preferences = preferences
        declared = {p.name for p in self.spec.case_column_presentations}
        for column, name in enumerate(self._table_columns):
            self.case_table.setColumnHidden(column, False)
            width = preferences.get(name, {}).get("width")
            if isinstance(width, int) and 40 <= width <= 1200:
                if name in declared:
                    width = max(width, self._header_width(column))
                self.case_table.setColumnWidth(column, width)

    def reset_columns(self) -> None:
        self._column_preferences = {}
        presentations = {p.name: p for p in self.spec.case_column_presentations}
        for c, name in enumerate(self._table_columns):
            role = (
                presentations[name].width_role
                if name in presentations
                else CaseColumnWidthRole.FALLBACK
            )
            self.case_table.setColumnWidth(c, self._initial_column_width(c, role))

    def _column_horizontal_padding(self) -> int:
        style = self.case_table.style()
        header = self.case_table.horizontalHeader()
        return 2 * (
            style.pixelMetric(
                QtWidgets.QStyle.PixelMetric.PM_HeaderMargin,
                None,
                header,
            )
            + style.pixelMetric(
                QtWidgets.QStyle.PixelMetric.PM_FocusFrameHMargin,
                None,
                self.case_table,
            )
        )

    def _column_text_width(self, text: str) -> int:
        return (
            self.case_table.fontMetrics().horizontalAdvance(text)
            + self._column_horizontal_padding()
        )

    def _needs_full_value_tooltip(
        self,
        text: str,
        width: int,
    ) -> bool:
        return self._column_text_width(text) > width

    def _header_width(self, column: int) -> int:
        header = self.case_table.horizontalHeader()
        header_padding = 2 * self.case_table.style().pixelMetric(
            QtWidgets.QStyle.PixelMetric.PM_HeaderMargin,
            None,
            header,
        )
        return header.sectionSizeHint(column) + header_padding

    def _initial_column_width(
        self,
        column: int,
        role: CaseColumnWidthRole,
    ) -> int:
        policy = _COLUMN_WIDTH_POLICIES[role]
        minimum = self._column_text_width(policy.minimum_text)
        preferred = self._column_text_width(policy.representative_text)
        maximum = self._column_text_width(policy.maximum_text)
        header = self.case_table.horizontalHeader()
        minimum = max(minimum, header.minimumSectionSize())
        if self._table_columns[column] == "stl_path":
            preferred = (
                self.case_table.fontMetrics().horizontalAdvance("geometry_part.stl")
                + self._column_horizontal_padding()
            )
            minimum = min(minimum, preferred)
        maximum = max(maximum, minimum)
        # Short flag values must not cap the width below their declared header.
        if any(
            p.name == self._table_columns[column]
            for p in self.spec.case_column_presentations
        ):
            maximum = max(maximum, self._header_width(column))
        return min(
            max(preferred, minimum, self._header_width(column)),
            maximum,
        )

    @staticmethod
    def _column_alignment(kind: CaseColumnKind) -> QtCore.Qt.AlignmentFlag:
        horizontal = QtCore.Qt.AlignmentFlag.AlignLeft
        if kind is CaseColumnKind.NUMERIC:
            horizontal = QtCore.Qt.AlignmentFlag.AlignRight
        elif kind is CaseColumnKind.FLAG:
            horizontal = QtCore.Qt.AlignmentFlag.AlignHCenter
        return horizontal | QtCore.Qt.AlignmentFlag.AlignVCenter

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
            self._clear_viewer_with_state(ArtifactViewState(ArtifactViewStatus.EMPTY))
            return
        self._auto_load_case_artifact(selected[0])

    def _clear_viewer_with_state(self, state: ArtifactViewState) -> None:
        """Preserve the clear signal, then project its reason synchronously."""
        if not isinstance(state, ArtifactViewState):
            raise TypeError("state must be an ArtifactViewState")
        self.viewer_clear_requested.emit()
        self.viewer_artifact_state_changed.emit(state)

    def _auto_load_case_artifact(self, row: CaseRow) -> None:
        case_id = str(row.get("case_id", "")).strip()
        if not case_id:
            self._clear_viewer_with_state(ArtifactViewState(ArtifactViewStatus.EMPTY))
            return
        if self.input_path is None:
            self._clear_viewer_with_state(ArtifactViewState(ArtifactViewStatus.EMPTY))
            return
        path = resolve_case_vtp_path(row, self.input_path)
        if self._vtp_artifact_key(case_id, path) in self._invalid_current_vtp_artifacts:
            self._clear_viewer_with_state(
                ArtifactViewState(ArtifactViewStatus.WRITE_FAILED, path, case_id)
            )
            return
        if not path.exists():
            self._clear_viewer_with_state(
                ArtifactViewState(ArtifactViewStatus.MISSING, path, case_id)
            )
            return
        try:
            artifact = self._artifact_reader(str(path))
        except Exception as exc:
            self._clear_viewer_with_state(
                ArtifactViewState(ArtifactViewStatus.READ_ERROR, path, case_id)
            )
            self.logln(f"[ERROR] Failed to read VTP: {exc}")
            return
        signature = self.spec.adapters.build_case_signature(row)
        state = automatic_artifact_view_state(artifact, row, signature, path)
        if state.status is ArtifactViewStatus.CURRENT:
            self.viewer_artifact_state_changed.emit(state)
            self.vtp_loaded.emit(str(path), artifact, row)
        else:
            self._clear_viewer_with_state(state)

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
        set_semantic_property(self.progress, "fluentStatus", "info")
        set_semantic_property(self.progress, "fluentBusy", True)
        self._set_running_state(True)
        self._cancel_requested = False
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
        self._cancel_requested = True
        self.progress.setFormat("Cancelling…")
        self._run_worker.cancel()
        self.btn_cancel.setEnabled(False)
        set_semantic_property(self.progress, "fluentStatus", "warning")
        set_semantic_property(self.progress, "fluentBusy", True)
        self.logln("[CANCEL] Cancellation requested...")

    def is_running(self) -> bool:
        return self._run_thread is not None

    @QtCore.Slot(int, int)
    def _on_run_progress(self, done: int, total: int) -> None:
        safe_total = max(int(total), 1)
        safe_done = min(max(int(done), 0), safe_total)
        self.progress.setRange(0, safe_total)
        self.progress.setValue(safe_done)
        self.progress.setFormat(
            f"Cancelling… {done}/{total}"
            if self._cancel_requested
            else f"{done}/{total}"
        )

    @QtCore.Slot(object)
    def _on_run_completed(self, result: GuiRunResult) -> None:
        self._update_current_vtp_artifact_validity(result)
        total = len(self._run_rows)
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(total)
        if result.output_issues:
            self.progress.setFormat("Completed with output errors")
            set_semantic_property(self.progress, "fluentStatus", "warning")
        else:
            self.progress.setFormat("Completed")
            set_semantic_property(self.progress, "fluentStatus", "success")
        set_semantic_property(self.progress, "fluentBusy", False)
        if self._run_output_path is not None and result.summary_csv_saved is not False:
            self.logln(f"[OK] Wrote results: {self._run_output_path}")
        if result.output_issues:
            QtWidgets.QMessageBox.warning(
                self,
                "Output Errors",
                self._output_error_summary(result),
            )
        self._refresh_first_result(result)

    @staticmethod
    def _vtp_artifact_key(case_id: object, path: str | Path) -> tuple[str, Path]:
        return (
            str(case_id).strip(),
            Path(path).expanduser().resolve(strict=False),
        )

    def _update_current_vtp_artifact_validity(self, result: GuiRunResult) -> None:
        """Replace current-run validity for the exact case/path identities run."""
        if self.input_path is None:
            return
        run_keys = {
            self._vtp_artifact_key(
                row.get("case_id", ""),
                resolve_case_vtp_path(row, self.input_path),
            )
            for row in self._run_rows
            if bool(int(row.get("save_vtp_on", 1)))
        }
        self._invalid_current_vtp_artifacts.difference_update(run_keys)
        invalidated_paths: set[Path] = set()
        for issue in result.output_issues:
            if (
                issue.kind is not OutputKind.VTP
                or issue.phase is not OutputPhase.WRITE
                or issue.case_id is None
            ):
                continue
            key = self._vtp_artifact_key(issue.case_id, issue.path)
            self._invalid_current_vtp_artifacts.add(key)
            invalidated_paths.add(key[1])
        for path in invalidated_paths:
            self.vtp_artifact_invalidated.emit(str(path))

    def _output_error_summary(self, result: GuiRunResult) -> str:
        """Build one bounded end-of-run notification from structured issues."""
        total = result.calculation_total_cases or len(self._run_rows)
        completed = result.calculation_completed_cases or total
        if result.summary_csv_saved is True:
            summary_status = "saved"
        elif result.summary_csv_saved is False:
            summary_status = "failed"
        else:
            summary_status = "not reported"
        vtp_failed = max(result.vtp_requested - result.vtp_saved, 0)
        lines = [
            "Run completed with output errors.",
            "",
            "Calculation:",
            f"  {completed}/{total} cases completed",
            "",
            "Output:",
            f"  Summary CSV: {summary_status}",
            f"  VTP: {result.vtp_saved} saved, {vtp_failed} failed",
            "",
            "Failed outputs:",
        ]
        shown = result.output_issues[:5]
        for issue in shown:
            if issue.kind is OutputKind.SUMMARY_CSV:
                label = "Summary CSV"
            elif issue.kind is OutputKind.OUTPUT_DIRECTORY:
                label = "Output directory"
            else:
                label = "VTP"
            case = f"{issue.case_id}: " if issue.case_id else f"{label}: "
            lines.append(f"  {case}{issue.message}")
        remaining = len(result.output_issues) - len(shown)
        if remaining:
            lines.append(f"  ... and {remaining} more")
        lines.extend(("", "See the log for full details."))
        return "\n".join(lines)

    def _refresh_first_result(self, result: GuiRunResult) -> None:
        if result.first_vtp_path is None:
            return
        row = (
            result.first_case_row
            if result.first_case_row is not None
            else (self._run_rows[0] if self._run_rows else None)
        )
        if row is None:
            self._clear_viewer_with_state(ArtifactViewState(ArtifactViewStatus.EMPTY))
            return
        path = result.first_vtp_path
        try:
            artifact = self._artifact_reader(str(path))
        except Exception as exc:
            case_id = str(row.get("case_id", "")).strip() or None
            self._clear_viewer_with_state(
                ArtifactViewState(ArtifactViewStatus.READ_ERROR, path, case_id)
            )
            self.logln(f"[ERROR] Failed to read VTP: {exc}")
            return
        signature = self.spec.adapters.build_case_signature(row)
        state = automatic_artifact_view_state(artifact, row, signature, path)
        if state.status is ArtifactViewStatus.CURRENT:
            self.viewer_artifact_state_changed.emit(state)
            self.vtp_loaded.emit(str(path), artifact, row)
        else:
            self._clear_viewer_with_state(state)

    @QtCore.Slot(str)
    def _on_run_failed(self, message: str) -> None:
        self.logln(f"[ERROR] {message}")
        self.progress.setFormat("Failed")
        set_semantic_property(self.progress, "fluentStatus", "danger")
        set_semantic_property(self.progress, "fluentBusy", False)

    @QtCore.Slot()
    def _on_run_canceled(self) -> None:
        self.logln("[CANCEL] Run canceled.")
        self.progress.setFormat("Canceled")
        set_semantic_property(self.progress, "fluentStatus", "warning")
        set_semantic_property(self.progress, "fluentBusy", False)

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
        self.btn_clear_selection.setEnabled(
            not running and bool(self.selected_case_rows())
        )
        self.btn_cancel.setEnabled(running)
        self.btn_run.setEnabled((not running) and bool(self.case_rows))

    def clear_loaded_cases(self) -> None:
        self._invalid_current_vtp_artifacts.clear()
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
        set_semantic_property(self.progress, "fluentStatus", "neutral")
        set_semantic_property(self.progress, "fluentBusy", False)
        self._clear_viewer_with_state(ArtifactViewState(ArtifactViewStatus.EMPTY))
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
        self.btn_clear_selection.setEnabled(
            selected > 0 and self.case_table.isEnabled()
        )
        self.lbl_run_scope.setText(
            "Load an input file to begin"
            if not total
            else f"Run scope: {selected} selected case(s)"
            if selected
            else f"Run scope: all {total} cases"
        )
        self._refresh_run_action()

    def _refresh_run_action(self) -> None:
        if not self.case_rows:
            text = "Run Cases"
        elif self.selected_case_rows():
            text = "Run Selected Cases"
        else:
            text = "Run All Cases"
        self.btn_run.setText(text)


__all__ = ("CasesPanel", "ValidationIssuesDialog")
