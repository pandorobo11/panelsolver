from __future__ import annotations

import hashlib
import os
import tempfile
import time
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtTest, QtWidgets

from fmfsolver._frontend import _legacy_gui_spec as fmf_solver_spec
from newtsolver._frontend import _legacy_gui_spec as newt_solver_spec
from panelsolver.app import (
    DEFAULT_CHECKPOINT_CASES,
    ArtifactSignatureCandidates,
    ArtifactViewStatus,
    GuiRunResult,
    OutputIssue,
    OutputKind,
    OutputPhase,
    SolverGuiAdapters,
)
from panelsolver.app.cases_panel import CasesPanel, ValidationIssuesDialog
from panelsolver.core import CaseSignature, canonical_json
from tests.path_assertions import assert_paths_equivalent


def _signature(label: str) -> CaseSignature:
    envelope = {"fixture": label}
    payload = canonical_json(envelope)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return CaseSignature(digest, payload, envelope)


def _adapters(rows, signatures, *, validator=None, reader=None):
    def read_cases(_path):
        if reader is not None:
            return reader(_path)
        return rows

    return SolverGuiAdapters(
        read_cases=read_cases,
        build_case_signatures=lambda row: signatures[str(row["case_id"])],
        run_cases=lambda _request: GuiRunResult(),
        validate_output_path=(
            validator if validator is not None else lambda out, _input, _rows: Path(out)
        ),
        resolve_velocity_hat_stl=lambda _row: (1.0, 0.0, 0.0),
    )


def _rows(out_dir="outputs"):
    return (
        {
            "case_id": "case_b",
            "stl_path": "/mesh/first.stl;/mesh/second.stl",
            "S": 5.0,
            "out_dir": str(out_dir),
            "custom": "first",
        },
        {
            "case_id": "case_a",
            "stl_path": "/mesh/third.stl",
            "S": 6.0,
            "out_dir": str(out_dir),
            "custom": "second",
        },
    )


class StructuredError(ValueError):
    def __init__(self) -> None:
        super().__init__("invalid")
        self.issues = (
            SimpleNamespace(
                row_number=2,
                case_id="bad",
                field="stl_path",
                message="is invalid",
            ),
        )


class CasesPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make_panel(
        self,
        rows=None,
        *,
        spec_factory=fmf_solver_spec,
        **kwargs,
    ):
        rows = _rows() if rows is None else rows
        signatures = {
            str(row["case_id"]): ArtifactSignatureCandidates(
                _signature(str(row["case_id"]))
            )
            for row in rows
        }
        spec = spec_factory(adapters=_adapters(rows, signatures, **kwargs))
        return CasesPanel(spec), signatures

    def wait_until(self, predicate, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while not predicate():
            self.app.processEvents()
            if time.monotonic() >= deadline:
                self.fail("timed out waiting for Qt lifecycle")
            time.sleep(0.002)
        self.app.processEvents()

    def test_load_renders_product_schema_extras_and_stl_names(self) -> None:
        panel, _signatures = self.make_panel()
        self.assertTrue(panel.load_input_file("/tmp/input.csv"))
        self.assertEqual("case_id", panel._table_columns[0])
        self.assertIn("S", panel._table_columns)
        self.assertNotIn("gamma", panel._table_columns)
        self.assertEqual("custom", panel._table_columns[-1])
        stl_column = panel._table_columns.index("stl_path")
        self.assertEqual(
            "first.stl, second.stl",
            panel.case_table.item(0, stl_column).text(),
        )
        self.assertFalse(
            bool(panel.case_table.editTriggers())
            and panel.case_table.editTriggers()
            != QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers
        )
        newt_rows = ({"case_id": "n", "gamma": 1.4, "stl_path": "n.stl"},)
        newt, _ = self.make_panel(newt_rows, spec_factory=newt_solver_spec)
        self.assertTrue(newt.load_input_file("/tmp/newt.csv"))
        self.assertIn("gamma", newt._table_columns)
        self.assertNotIn("S", newt._table_columns)

    def test_product_headers_use_documented_labels_and_source_units(self) -> None:
        cases = (
            (
                fmf_solver_spec,
                {
                    "case_id": "Case ID",
                    "stl_path": "STL",
                    "stl_scale_m_per_unit": "STL scale [m/STL unit]",
                    "Mach": "Mach",
                    "Altitude_km": "Altitude [km]",
                    "Tw_K": "Tw [K]",
                    "alpha_deg": "Alpha [deg]",
                    "Aref_m2": "Aref [m²]",
                },
            ),
            (
                newt_solver_spec,
                {
                    "case_id": "Case ID",
                    "stl_path": "STL",
                    "stl_scale_m_per_unit": "STL scale [m/STL unit]",
                    "Mach": "Mach",
                    "gamma": "Gamma",
                    "windward_eq": "Windward equation",
                    "leeward_eq": "Leeward equation",
                    "alpha_deg": "Alpha [deg]",
                    "Aref_m2": "Aref [m²]",
                },
            ),
        )
        for spec_factory, expected in cases:
            with self.subTest(domain=spec_factory.__module__):
                rows = ({"case_id": "one", "stl_path": "/mesh/one.stl"},)
                panel, _ = self.make_panel(rows, spec_factory=spec_factory)
                self.assertTrue(panel.load_input_file("/tmp/input.csv"))
                actual = {
                    name: panel.case_table.horizontalHeaderItem(
                        panel._table_columns.index(name)
                    ).text()
                    for name in expected
                }
                self.assertEqual(expected, actual)

    def test_column_categories_project_to_engineering_alignment(self) -> None:
        rows = (
            {
                "case_id": "one",
                "stl_path": "/mesh/one.stl",
                "Mach": 8.0,
                "alpha_deg": 1.25,
                "Aref_m2": 2.5,
                "ref_x_m": -0.5,
                "windward_eq": "newtonian",
                "ray_backend": "auto",
                "shielding_on": 0,
                "save_vtp_on": 1,
                "custom": "left fallback",
            },
        )
        panel, _ = self.make_panel(rows, spec_factory=newt_solver_spec)
        self.assertTrue(panel.load_input_file("/tmp/input.csv"))

        def alignment(name: str) -> QtCore.Qt.AlignmentFlag:
            item = panel.case_table.item(0, panel._table_columns.index(name))
            return QtCore.Qt.AlignmentFlag(item.textAlignment())

        for name in ("Mach", "alpha_deg", "Aref_m2", "ref_x_m"):
            with self.subTest(name=name):
                self.assertTrue(alignment(name) & QtCore.Qt.AlignmentFlag.AlignRight)
                self.assertTrue(alignment(name) & QtCore.Qt.AlignmentFlag.AlignVCenter)
        for name in (
            "case_id",
            "stl_path",
            "windward_eq",
            "ray_backend",
            "custom",
        ):
            with self.subTest(name=name):
                self.assertTrue(alignment(name) & QtCore.Qt.AlignmentFlag.AlignLeft)
                self.assertTrue(alignment(name) & QtCore.Qt.AlignmentFlag.AlignVCenter)
        for name in ("shielding_on", "save_vtp_on"):
            with self.subTest(name=name):
                self.assertTrue(alignment(name) & QtCore.Qt.AlignmentFlag.AlignHCenter)
                self.assertTrue(alignment(name) & QtCore.Qt.AlignmentFlag.AlignVCenter)

        custom_column = panel._table_columns.index("custom")
        self.assertEqual(
            "custom", panel.case_table.horizontalHeaderItem(custom_column).text()
        )

    def test_cell_text_precision_and_existing_identities_are_preserved(self) -> None:
        long_decimal = Decimal("1.2345678901234567890123456789")
        scientific = 1e-12
        row = {
            "case_id": "exact",
            "stl_path": "/mesh/body.stl;/mesh/fin.stl",
            "stl_scale_m_per_unit": 1,
            "S": 5.0,
            "Ti_K": None,
            "Mach": long_decimal,
            "Altitude_km": scientific,
            "Tw_K": 300.0,
            "ray_backend": "rtree",
            "shielding_on": 0,
            "save_vtp_on": 1,
            "custom": Decimal("9.876543210987654321"),
        }
        panel, _ = self.make_panel((row,))
        self.assertTrue(panel.load_input_file("/tmp/input.csv"))
        self.assertEqual(
            (*panel.spec.case_columns, "custom"),
            panel._table_columns,
        )

        expected = {
            "case_id": "exact",
            "stl_scale_m_per_unit": "1",
            "S": "5.0",
            "Ti_K": "",
            "Mach": str(long_decimal),
            "Altitude_km": str(scientific),
            "Tw_K": "300.0",
            "ray_backend": "rtree",
            "shielding_on": "0",
            "save_vtp_on": "1",
            "custom": "9.876543210987654321",
        }
        for name, text in expected.items():
            with self.subTest(name=name):
                column = panel._table_columns.index(name)
                self.assertEqual(text, panel.case_table.item(0, column).text())

        stl_column = panel._table_columns.index("stl_path")
        stl_item = panel.case_table.item(0, stl_column)
        self.assertEqual("body.stl, fin.stl", stl_item.text())
        self.assertEqual(row["stl_path"], stl_item.toolTip())
        self.assertEqual(
            0,
            panel.case_table.item(0, 0).data(QtCore.Qt.ItemDataRole.UserRole),
        )

    def test_semantic_initial_widths_fit_headers_and_preserve_native_resize(
        self,
    ) -> None:
        rows = (
            {
                "case_id": "case-000001",
                "stl_path": "geometry/vehicle.stl",
                "stl_scale_m_per_unit": "1.234567e-12",
                "Mach": "12.5",
                "gamma": "1.4",
                "windward_eq": "modified_newtonian",
                "leeward_eq": "prandtl_meyer",
                "alpha_deg": "-12.5",
                "beta_or_bank_deg": "2.5",
                "attitude_input": "beta_sin",
                "ref_x_m": "-1.234567e+12",
                "ref_y_m": "0.0",
                "ref_z_m": "1.234567e-12",
                "Aref_m2": "1.234567e+12",
                "Lref_Cl_m": "1.234567e+12",
                "Lref_Cm_m": "1.234567e+12",
                "Lref_Cn_m": "1.234567e+12",
                "shielding_on": 1,
                "ray_backend": "embree",
                "out_dir": "outputs/engineering-results",
                "save_vtp_on": 1,
                "custom": "sample value",
            },
        )
        panel, _ = self.make_panel(rows, spec_factory=newt_solver_spec)
        with patch.object(
            QtWidgets.QTableWidget,
            "resizeColumnsToContents",
            side_effect=AssertionError("content autosizing must not be used"),
        ):
            self.assertTrue(panel.load_input_file("/tmp/input.csv"))

        def width(name: str) -> int:
            return panel.case_table.columnWidth(panel._table_columns.index(name))

        header = panel.case_table.horizontalHeader()
        for column, name in enumerate(panel._table_columns):
            with self.subTest(header=name):
                self.assertGreaterEqual(
                    panel.case_table.columnWidth(column),
                    header.sectionSizeHint(column),
                )

        self.assertEqual(width("Mach"), width("gamma"))
        self.assertEqual(width("ref_x_m"), width("ref_y_m"))
        self.assertEqual(width("ref_y_m"), width("ref_z_m"))
        self.assertEqual(width("ref_z_m"), width("Aref_m2"))
        self.assertEqual(width("stl_path"), width("out_dir"))
        self.assertLess(width("shielding_on"), width("stl_path"))
        self.assertLess(width("save_vtp_on"), width("windward_eq"))
        self.assertLess(width("ray_backend"), width("windward_eq"))

        mach_column = panel._table_columns.index("Mach")
        self.assertEqual(
            QtWidgets.QHeaderView.ResizeMode.Interactive,
            header.sectionResizeMode(mach_column),
        )
        initial = width("Mach")
        panel.case_table.setColumnWidth(mach_column, initial + 37)
        self.assertEqual(initial + 37, width("Mach"))

        panel.resize(400, 500)
        panel.show()
        self.app.processEvents()
        self.assertGreater(panel.case_table.horizontalScrollBar().maximum(), 0)
        panel.close()

    def test_declared_and_fallback_widths_are_stable_against_outliers(self) -> None:
        ordinary = (
            {
                "case_id": f"case-{index}",
                "stl_path": f"geometry/body-{index}.stl",
                "windward_eq": "newtonian",
                "out_dir": "outputs/results",
                "custom": "ordinary",
            }
            for index in range(3)
        )
        ordinary_rows = tuple(ordinary)
        outlier_rows = (
            *ordinary_rows[:2],
            {
                "case_id": "case-" + "identifier-" * 30,
                "stl_path": "/volume/" + "nested-component/" * 30 + "body.stl",
                "windward_eq": "unexpected_model_selector_" * 20,
                "out_dir": "results/" + "long-output-directory/" * 30,
                "custom": "unexpected-extra-value-" * 30,
            },
        )
        ordinary_panel, _ = self.make_panel(
            ordinary_rows,
            spec_factory=newt_solver_spec,
        )
        outlier_panel, _ = self.make_panel(
            outlier_rows,
            spec_factory=newt_solver_spec,
        )
        self.assertTrue(ordinary_panel.load_input_file("/tmp/ordinary.csv"))
        self.assertTrue(outlier_panel.load_input_file("/tmp/outlier.csv"))

        for name in (
            "case_id",
            "stl_path",
            "windward_eq",
            "out_dir",
            "custom",
        ):
            with self.subTest(name=name):
                ordinary_column = ordinary_panel._table_columns.index(name)
                outlier_column = outlier_panel._table_columns.index(name)
                self.assertEqual(
                    ordinary_panel.case_table.columnWidth(ordinary_column),
                    outlier_panel.case_table.columnWidth(outlier_column),
                )

        long_row = outlier_rows[-1]
        tooltip_columns = ("case_id", "windward_eq", "out_dir", "custom")
        for name in tooltip_columns:
            with self.subTest(tooltip=name):
                column = outlier_panel._table_columns.index(name)
                item = outlier_panel.case_table.item(2, column)
                self.assertEqual(str(long_row[name]), item.text())
                self.assertEqual(str(long_row[name]), item.toolTip())

        stl_column = outlier_panel._table_columns.index("stl_path")
        stl_item = outlier_panel.case_table.item(2, stl_column)
        self.assertEqual("body.stl", stl_item.text())
        self.assertEqual(long_row["stl_path"], stl_item.toolTip())

    def test_bounded_numeric_width_preserves_extreme_exact_text_without_tooltip(
        self,
    ) -> None:
        extreme = Decimal("1.23456789012345678901234567890123456789")
        row = {
            "case_id": "numeric-outlier",
            "stl_path": "body.stl",
            "Mach": extreme,
            "gamma": "1.234567e+123",
            "alpha_deg": "-9.876543210987654321e-123",
        }
        panel, _ = self.make_panel((row,), spec_factory=newt_solver_spec)
        self.assertTrue(panel.load_input_file("/tmp/input.csv"))
        for name in ("Mach", "gamma", "alpha_deg"):
            with self.subTest(name=name):
                column = panel._table_columns.index(name)
                item = panel.case_table.item(0, column)
                self.assertEqual(str(row[name]), item.text())
                self.assertEqual("", item.toolTip())

    def test_short_wide_text_uses_rendered_width_for_tooltip(self) -> None:
        short_text = "界"
        row = {
            "case_id": "short-wide-text",
            "stl_path": "body.stl",
            "custom": short_text,
        }
        panel, _ = self.make_panel((row,))
        original_text_width = panel._column_text_width

        def controlled_text_width(text: str) -> int:
            if text == short_text:
                return 10_000
            return original_text_width(text)

        self.assertLessEqual(len(short_text), len("sample value"))
        with patch.object(
            panel,
            "_column_text_width",
            side_effect=controlled_text_width,
        ) as text_width:
            self.assertTrue(panel.load_input_file("/tmp/input.csv"))

        text_width.assert_any_call(short_text)
        column = panel._table_columns.index("custom")
        item = panel.case_table.item(0, column)
        self.assertEqual(short_text, item.text())
        self.assertEqual(short_text, item.toolTip())

    def test_long_unknown_header_uses_bounded_fallback_and_exact_tooltips(
        self,
    ) -> None:
        extra_name = "custom_engineering_metadata_" * 12
        extra_value = "exact-extra-value-" * 30
        row = {
            "case_id": "fallback",
            "stl_path": "body.stl",
            extra_name: extra_value,
        }
        panel, _ = self.make_panel((row,))
        self.assertTrue(panel.load_input_file("/tmp/input.csv"))
        column = panel._table_columns.index(extra_name)
        header_item = panel.case_table.horizontalHeaderItem(column)
        item = panel.case_table.item(0, column)
        self.assertEqual(extra_name, header_item.text())
        self.assertEqual(extra_name, header_item.toolTip())
        self.assertLess(
            panel.case_table.columnWidth(column),
            panel._column_text_width(extra_name),
        )
        self.assertEqual(extra_value, item.text())
        self.assertEqual(extra_value, item.toolTip())

    def test_shared_panel_uses_spec_metadata_without_product_branching(self) -> None:
        def renamed_spec(*, adapters):
            return replace(
                fmf_solver_spec(adapters=adapters),
                product_id="synthetic-product",
            )

        panel, _ = self.make_panel(spec_factory=renamed_spec)
        self.assertTrue(panel.load_input_file("/tmp/input.csv"))
        mach_column = panel._table_columns.index("Mach")
        self.assertEqual(
            "Mach", panel.case_table.horizontalHeaderItem(mach_column).text()
        )
        self.assertTrue(
            QtCore.Qt.AlignmentFlag(
                panel.case_table.item(0, mach_column).textAlignment()
            )
            & QtCore.Qt.AlignmentFlag.AlignRight
        )

    def test_semantic_action_roles_preserve_enabled_and_click_behavior(self) -> None:
        panel, _ = self.make_panel()
        self.assertEqual("secondary", panel.btn_pick_input.property("fluentAppearance"))
        self.assertEqual("primary", panel.btn_run.property("fluentAppearance"))
        self.assertEqual("danger", panel.btn_cancel.property("fluentAppearance"))
        self.assertTrue(panel.btn_pick_input.isEnabled())
        self.assertEqual("Run Cases", panel.btn_run.text())
        self.assertFalse(panel.btn_run.isEnabled())
        self.assertFalse(panel.btn_cancel.isEnabled())

        picks: list[bool] = []
        runs: list[bool] = []
        cancels: list[bool] = []
        panel.btn_pick_input.clicked.connect(
            lambda checked=False: picks.append(checked)
        )
        panel.btn_run.clicked.connect(lambda checked=False: runs.append(checked))
        panel.btn_cancel.clicked.connect(lambda checked=False: cancels.append(checked))
        with patch.object(
            QtWidgets.QFileDialog,
            "getOpenFileName",
            return_value=("", ""),
        ):
            panel.btn_pick_input.click()
        panel.btn_run.click()
        panel.btn_cancel.click()
        self.assertEqual([False], picks)
        self.assertEqual([], runs)
        self.assertEqual([], cancels)

        self.assertTrue(panel.load_input_file("/tmp/input.csv"))
        with patch.object(
            QtWidgets.QFileDialog,
            "getSaveFileName",
            return_value=("", ""),
        ):
            panel.btn_run.click()
        self.assertEqual([False], runs)

    def test_execution_controls_use_fixed_settings_and_status_action_rows(self) -> None:
        panel, _ = self.make_panel()
        root = panel.layout()

        self.assertIs(panel.settings_row, root.itemAt(3).layout())
        self.assertIs(panel.execution_row, root.itemAt(4).layout())
        self.assertIsNone(root.itemAt(4).widget())

        self.assertEqual(4, panel.settings_row.count())
        self.assertIs(panel.workers_group, panel.settings_row.itemAt(0).layout())
        settings_gap = panel.settings_row.itemAt(1).spacerItem()
        self.assertIsNotNone(settings_gap)
        self.assertIs(panel.checkpoint_group, panel.settings_row.itemAt(2).layout())
        settings_stretch = panel.settings_row.itemAt(3).spacerItem()
        self.assertIsNotNone(settings_stretch)
        self.assertEqual(
            QtWidgets.QSizePolicy.Policy.Expanding,
            settings_stretch.sizePolicy().horizontalPolicy(),
        )

        self.assertEqual(
            [panel.lbl_workers, panel.spin_workers],
            [panel.workers_group.itemAt(index).widget() for index in range(2)],
        )
        self.assertEqual(
            [
                panel.lbl_checkpoint_every_cases,
                panel.spin_checkpoint_every_cases,
                panel.lbl_checkpoint_unit,
            ],
            [panel.checkpoint_group.itemAt(index).widget() for index in range(3)],
        )
        self.assertEqual(2, panel.execution_row.count())
        self.assertIs(panel.progress, panel.execution_row.itemAt(0).widget())
        self.assertEqual(1, panel.execution_row.stretch(0))
        self.assertTrue(
            panel.execution_row.itemAt(0).alignment()
            & QtCore.Qt.AlignmentFlag.AlignVCenter
        )
        self.assertIs(
            panel.run_actions_group,
            panel.execution_row.itemAt(1).layout(),
        )
        self.assertEqual(
            [panel.btn_run, panel.btn_cancel],
            [panel.run_actions_group.itemAt(index).widget() for index in range(2)],
        )
        self.assertLess(
            panel.workers_group.spacing(),
            settings_gap.sizeHint().width(),
        )
        self.assertLess(
            panel.checkpoint_group.spacing(),
            settings_gap.sizeHint().width(),
        )
        self.assertEqual(8, panel.run_actions_group.spacing())
        self.assertEqual(8, panel.execution_row.spacing())

        for group in (
            panel.workers_group,
            panel.checkpoint_group,
            panel.run_actions_group,
        ):
            margins = group.contentsMargins()
            self.assertEqual(
                (0, 0, 0, 0),
                (margins.left(), margins.top(), margins.right(), margins.bottom()),
            )

    def test_diagnostics_toggle_preserves_hidden_log_content(self) -> None:
        panel, _ = self.make_panel()
        panel.show()
        self.app.processEvents()
        try:
            self.assertEqual("Diagnostics", panel.btn_diagnostics.text())
            self.assertEqual(
                "subtle",
                panel.btn_diagnostics.property("fluentAppearance"),
            )
            self.assertTrue(panel.btn_diagnostics.property("diagnosticsDisclosure"))
            self.assertEqual(
                QtWidgets.QSizePolicy.Policy.Expanding,
                panel.btn_diagnostics.sizePolicy().horizontalPolicy(),
            )
            self.assertEqual(
                QtWidgets.QSizePolicy.Policy.Fixed,
                panel.btn_diagnostics.sizePolicy().verticalPolicy(),
            )
            self.assertEqual(
                panel.layout().contentsRect().width(),
                panel.btn_diagnostics.width(),
            )
            self.assertGreater(
                panel.btn_diagnostics.width(),
                panel.btn_diagnostics.sizeHint().width(),
            )
            self.assertFalse(panel.btn_diagnostics.isChecked())
            self.assertEqual(
                QtCore.Qt.ArrowType.RightArrow,
                panel.btn_diagnostics.arrowType(),
            )
            self.assertEqual(QtCore.QSize(12, 12), panel.btn_diagnostics.iconSize())
            self.assertEqual(
                QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon,
                panel.btn_diagnostics.toolButtonStyle(),
            )
            self.assertEqual("Diagnostics", panel.btn_diagnostics.accessibleName())
            self.assertEqual(
                "Show diagnostic log",
                panel.btn_diagnostics.accessibleDescription(),
            )
            self.assertEqual("Show diagnostic log", panel.btn_diagnostics.toolTip())
            self.assertTrue(panel.btn_diagnostics.shortcut().isEmpty())
            self.assertTrue(
                panel.btn_diagnostics.focusPolicy() & QtCore.Qt.FocusPolicy.TabFocus
            )
            self.assertIsInstance(panel.log, QtWidgets.QPlainTextEdit)
            self.assertTrue(panel.log.isReadOnly())
            self.assertEqual(8000, panel.log.maximumBlockCount())
            self.assertEqual(180, panel.log.minimumHeight())
            self.assertTrue(panel.log.isHidden())
            self.assertTrue(panel.progress.isVisible())

            panel.logln("[TEST] hidden message")
            self.assertIn("[TEST] hidden message", panel.log.toPlainText())

            panel.btn_diagnostics.click()
            self.app.processEvents()
            self.assertTrue(panel.btn_diagnostics.isChecked())
            self.assertEqual(
                QtCore.Qt.ArrowType.DownArrow,
                panel.btn_diagnostics.arrowType(),
            )
            self.assertTrue(panel.log.isVisible())
            self.assertIn("[TEST] hidden message", panel.log.toPlainText())
            self.assertEqual(
                "Hide diagnostic log",
                panel.btn_diagnostics.accessibleDescription(),
            )
            self.assertEqual("Hide diagnostic log", panel.btn_diagnostics.toolTip())

            panel.btn_diagnostics.click()
            self.app.processEvents()
            self.assertFalse(panel.btn_diagnostics.isChecked())
            self.assertEqual(
                QtCore.Qt.ArrowType.RightArrow,
                panel.btn_diagnostics.arrowType(),
            )
            self.assertTrue(panel.log.isHidden())
            self.assertIn("[TEST] hidden message", panel.log.toPlainText())
            self.assertEqual(
                "Show diagnostic log",
                panel.btn_diagnostics.accessibleDescription(),
            )
            self.assertEqual("Show diagnostic log", panel.btn_diagnostics.toolTip())

            panel.btn_diagnostics.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
            self.assertTrue(panel.btn_diagnostics.hasFocus())
            QtTest.QTest.keyClick(
                panel.btn_diagnostics,
                QtCore.Qt.Key.Key_Space,
            )
            self.assertTrue(panel.btn_diagnostics.isChecked())
            self.assertTrue(panel.log.isVisible())
        finally:
            panel.close()

    def test_diagnostics_choice_survives_input_load_and_clear(self) -> None:
        panel, _ = self.make_panel()
        panel.btn_diagnostics.click()
        self.assertTrue(panel.btn_diagnostics.isChecked())
        self.assertFalse(panel.log.isHidden())

        self.assertTrue(panel.load_input_file("/tmp/input.csv"))
        self.assertTrue(panel.btn_diagnostics.isChecked())
        self.assertFalse(panel.log.isHidden())
        panel.clear_loaded_cases()
        self.assertTrue(panel.btn_diagnostics.isChecked())
        self.assertFalse(panel.log.isHidden())

        panel.btn_diagnostics.click()
        self.assertFalse(panel.btn_diagnostics.isChecked())
        self.assertTrue(panel.log.isHidden())
        self.assertTrue(panel.load_input_file("/tmp/other.csv"))
        panel.clear_loaded_cases()
        self.assertFalse(panel.btn_diagnostics.isChecked())
        self.assertTrue(panel.log.isHidden())

    def test_run_action_projects_case_and_selection_scope(self) -> None:
        panel, _ = self.make_panel()
        self.assertEqual("Run Cases", panel.btn_run.text())
        self.assertFalse(panel.btn_run.isEnabled())

        self.assertTrue(panel.load_input_file("/tmp/input.csv"))
        self.assertEqual("Run All Cases", panel.btn_run.text())
        self.assertTrue(panel.btn_run.isEnabled())
        self.assertEqual(
            ["case_b", "case_a"],
            [row["case_id"] for row in panel.selected_or_all_case_rows()],
        )

        selection = panel.case_table.selectionModel()
        selection.select(
            panel.case_table.model().index(1, 0),
            QtCore.QItemSelectionModel.SelectionFlag.Select
            | QtCore.QItemSelectionModel.SelectionFlag.Rows,
        )
        self.assertEqual("Run Selected Cases", panel.btn_run.text())
        self.assertEqual(
            ["case_a"],
            [row["case_id"] for row in panel.selected_or_all_case_rows()],
        )

        selection.select(
            panel.case_table.model().index(0, 0),
            QtCore.QItemSelectionModel.SelectionFlag.Select
            | QtCore.QItemSelectionModel.SelectionFlag.Rows,
        )
        self.assertEqual("Run Selected Cases", panel.btn_run.text())
        self.assertEqual(
            ["case_b", "case_a"],
            [row["case_id"] for row in panel.selected_or_all_case_rows()],
        )

        panel.case_table.clearSelection()
        self.assertEqual("Run All Cases", panel.btn_run.text())
        self.assertEqual(
            ["case_b", "case_a"],
            [row["case_id"] for row in panel.selected_or_all_case_rows()],
        )

        panel.clear_loaded_cases()
        self.assertEqual("Run Cases", panel.btn_run.text())
        self.assertFalse(panel.btn_run.isEnabled())

    def test_input_picker_offers_only_current_case_table_formats(self) -> None:
        panel, _ = self.make_panel()
        with patch.object(
            QtWidgets.QFileDialog,
            "getOpenFileName",
            return_value=("", ""),
        ) as choose:
            panel.pick_input_file()
        self.assertEqual(
            "CSV/Excel (*.csv *.xlsx *.xlsm)",
            choose.call_args.args[3],
        )

    def test_input_picker_uses_cwd_initially(self) -> None:
        panel, _ = self.make_panel()
        with patch.object(
            QtWidgets.QFileDialog,
            "getOpenFileName",
            return_value=("", ""),
        ) as choose:
            panel.pick_input_file()
        self.assertEqual(Path.cwd(), Path(choose.call_args.args[2]))

    def test_success_updates_last_input_directory_and_failure_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remembered = root / "remembered"
            remembered.mkdir()
            rows = _rows()

            def read_cases(path):
                if Path(path).name == "bad.csv":
                    raise ValueError("broken input")
                return rows

            panel, _ = self.make_panel(rows, reader=read_cases)
            self.assertTrue(panel.load_input_file(remembered / "input.csv"))
            self.assertEqual(remembered, panel.input_dialog_directory())

            with patch.object(QtWidgets.QMessageBox, "critical"):
                self.assertFalse(panel.load_input_file(root / "other" / "bad.csv"))
            self.assertEqual((), panel.case_rows)
            self.assertIsNone(panel.input_path)
            self.assertEqual(remembered, panel.input_dialog_directory())

    def test_later_input_picker_starts_from_successfully_loaded_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            panel, _ = self.make_panel()
            panel.load_input_file(root / "input.csv")
            with patch.object(
                QtWidgets.QFileDialog,
                "getOpenFileName",
                return_value=("", ""),
            ) as choose:
                panel.pick_input_file()
            self.assertEqual(root, Path(choose.call_args.args[2]))
            self.assertEqual(root, panel.input_dialog_directory())

    def test_new_panel_forgets_previous_session_input_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            previous, _ = self.make_panel()
            self.assertTrue(previous.load_input_file(root / "input.csv"))
            self.assertEqual(root, previous.input_dialog_directory())

            restarted, _ = self.make_panel()
            self.assertEqual(Path.cwd(), restarted.input_dialog_directory())

    def test_missing_session_input_directory_falls_back_to_cwd(self) -> None:
        panel, _ = self.make_panel()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertTrue(panel.load_input_file(root / "input.csv"))
            self.assertEqual(root, panel.input_dialog_directory())
        self.assertEqual(Path.cwd(), panel.input_dialog_directory())

    def test_example_load_does_not_update_last_input_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remembered = root / "normal"
            remembered.mkdir()
            panel, _ = self.make_panel()
            self.assertTrue(panel.load_input_file(remembered / "input.csv"))
            self.assertTrue(
                panel.load_input_file(
                    root / "example" / "fmf" / "basic.csv",
                    remember_directory=False,
                )
            )
            self.assertEqual(remembered, panel.input_dialog_directory())

    def test_selected_rows_keep_table_order_and_no_selection_means_all(self) -> None:
        panel, _ = self.make_panel()
        panel.load_input_file("/tmp/input.csv")
        self.assertEqual(
            ["case_b", "case_a"],
            [r["case_id"] for r in panel.selected_or_all_case_rows()],
        )
        selection = panel.case_table.selectionModel()
        selection.select(
            panel.case_table.model().index(1, 0),
            QtCore.QItemSelectionModel.SelectionFlag.Select
            | QtCore.QItemSelectionModel.SelectionFlag.Rows,
        )
        selection.select(
            panel.case_table.model().index(0, 0),
            QtCore.QItemSelectionModel.SelectionFlag.Select
            | QtCore.QItemSelectionModel.SelectionFlag.Rows,
        )
        self.assertEqual(
            ["case_b", "case_a"], [r["case_id"] for r in panel.selected_case_rows()]
        )

    def test_selected_case_signal_tracks_batch_export_availability(self) -> None:
        panel, _ = self.make_panel()
        emitted = []
        panel.selected_cases_changed.connect(emitted.append)
        panel.load_input_file("/tmp/input.csv")
        self.assertEqual((), emitted[-1])
        panel.case_table.selectRow(0)
        self.assertEqual(("case_b",), tuple(row["case_id"] for row in emitted[-1]))
        panel.case_table.clearSelection()
        self.assertEqual((), emitted[-1])

    def test_automatic_artifact_requires_current_signature_and_clears_otherwise(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="phase6_cases_") as directory:
            rows = _rows(directory)
            panel, signatures = self.make_panel(rows)
            panel.load_input_file(Path(directory) / "input.csv")
            Path(directory, "case_b.vtp").write_text("fixture", encoding="utf-8")
            current = SimpleNamespace(
                field_data={
                    "case_id": ["case_b"],
                    "case_signature": [signatures["case_b"].primary.digest],
                }
            )
            panel._artifact_reader = lambda _path: current
            loaded: list[tuple] = []
            cleared: list[bool] = []
            states = []
            panel.vtp_loaded.connect(lambda *args: loaded.append(args))
            panel.viewer_clear_requested.connect(lambda: cleared.append(True))
            panel.viewer_artifact_state_changed.connect(states.append)
            panel.case_table.selectRow(0)
            self.assertEqual(1, len(loaded))
            self.assertEqual("case_b", loaded[0][2]["case_id"])
            self.assertEqual(ArtifactViewStatus.CURRENT, states[-1].status)
            self.assertEqual(Path(directory, "case_b.vtp").resolve(), states[-1].path)

            stale = _signature("stale")
            current.field_data["case_signature"] = [stale.digest]
            panel.on_case_selection_changed()
            self.assertTrue(cleared)
            self.assertEqual(ArtifactViewStatus.STALE, states[-1].status)
            self.assertEqual("case_b", states[-1].case_id)

            current.field_data["case_id"] = ["other"]
            panel.on_case_selection_changed()
            self.assertEqual(ArtifactViewStatus.MISMATCHED, states[-1].status)
            panel.case_table.clearSelection()
            self.assertGreaterEqual(len(cleared), 2)
            self.assertEqual(ArtifactViewStatus.EMPTY, states[-1].status)

    def test_accepted_legacy_signature_remains_current_automatic_result(self) -> None:
        with tempfile.TemporaryDirectory(prefix="legacy_viewer_state_") as directory:
            rows = _rows(directory)
            primary = _signature("primary")
            legacy = _signature("legacy")
            signatures = {
                "case_b": ArtifactSignatureCandidates(primary, (legacy.digest,)),
                "case_a": ArtifactSignatureCandidates(_signature("case_a")),
            }
            panel = CasesPanel(
                fmf_solver_spec(adapters=_adapters(rows, signatures)),
                artifact_reader=lambda _path: SimpleNamespace(
                    field_data={
                        "case_id": ["case_b"],
                        "case_signature": [legacy.digest],
                    }
                ),
            )
            panel.load_input_file(Path(directory) / "input.csv")
            Path(directory, "case_b.vtp").write_text("fixture", encoding="utf-8")
            states = []
            loaded = []
            panel.viewer_artifact_state_changed.connect(states.append)
            panel.vtp_loaded.connect(lambda *args: loaded.append(args))
            panel.case_table.selectRow(0)
            self.assertEqual(1, len(loaded))
            self.assertEqual(ArtifactViewStatus.CURRENT, states[-1].status)

    def test_automatic_artifact_resolves_relative_out_dir_from_input_parent(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="gui_relative_vtp_") as directory:
            root = Path(directory)
            rows = _rows("outputs")
            panel, signatures = self.make_panel(rows)
            panel.load_input_file(root / "input.csv")
            artifact_path = root / "outputs" / "case_b.vtp"
            artifact_path.parent.mkdir()
            artifact_path.write_text("fixture", encoding="utf-8")
            seen = []
            panel._artifact_reader = lambda path: (
                seen.append(Path(path))
                or SimpleNamespace(
                    field_data={
                        "case_id": ["case_b"],
                        "case_signature": [signatures["case_b"].primary.digest],
                    }
                )
            )
            panel.case_table.selectRow(0)
            self.assertEqual(1, len(seen))
            assert_paths_equivalent(self, artifact_path, seen[0])

    def test_missing_and_broken_artifacts_clear_previous_view(self) -> None:
        with tempfile.TemporaryDirectory(prefix="phase6_cases_") as directory:
            rows = _rows(directory)
            panel, _ = self.make_panel(rows)
            panel.load_input_file(Path(directory) / "input.csv")
            cleared: list[bool] = []
            states = []
            events = []
            panel.viewer_clear_requested.connect(lambda: cleared.append(True))
            panel.viewer_artifact_state_changed.connect(states.append)
            panel.viewer_clear_requested.connect(lambda: events.append("clear"))
            panel.viewer_artifact_state_changed.connect(
                lambda state: events.append(state.status)
            )
            panel.case_table.selectRow(0)
            self.assertTrue(cleared)
            self.assertEqual(ArtifactViewStatus.MISSING, states[-1].status)
            self.assertEqual(
                ["clear", ArtifactViewStatus.MISSING],
                events[-2:],
            )
            self.assertEqual("case_b", states[-1].case_id)
            self.assertEqual(Path(directory, "case_b.vtp").resolve(), states[-1].path)
            Path(directory, "case_b.vtp").write_text("fixture", encoding="utf-8")
            panel._artifact_reader = lambda _path: (_ for _ in ()).throw(
                ValueError("broken")
            )
            panel.on_case_selection_changed()
            self.assertEqual(ArtifactViewStatus.READ_ERROR, states[-1].status)
            self.assertIn("Failed to read VTP", panel.log.toPlainText())

    def test_vtp_suppression_uses_case_and_path_and_resets_with_input_state(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="gui_vtp_validity_") as directory:
            root = Path(directory)
            first_dir = root / "first"
            second_dir = root / "second"
            first_dir.mkdir()
            second_dir.mkdir()
            first_path = first_dir / "same.vtp"
            second_path = second_dir / "same.vtp"
            first_path.write_text("old first", encoding="utf-8")
            second_path.write_text("old second", encoding="utf-8")
            first_row = {"case_id": "same", "out_dir": str(first_dir)}
            second_row = {"case_id": "same", "out_dir": str(second_dir)}
            panel, signatures = self.make_panel((first_row,))
            panel.load_input_file(root / "input.csv")
            artifact = SimpleNamespace(
                field_data={
                    "case_id": ["same"],
                    "case_signature": [signatures["same"].primary.digest],
                }
            )
            reads: list[Path] = []
            panel._artifact_reader = lambda path: reads.append(Path(path)) or artifact
            states = []
            panel.viewer_artifact_state_changed.connect(states.append)
            issue = OutputIssue(
                OutputKind.VTP,
                OutputPhase.WRITE,
                str(first_path),
                "save failed",
                "same",
            )
            panel._run_rows = (first_row,)
            with patch.object(QtWidgets.QMessageBox, "warning"):
                panel._on_run_completed(GuiRunResult(output_issues=(issue,)))

            panel._auto_load_case_artifact(first_row)
            self.assertEqual([], reads)
            self.assertEqual(ArtifactViewStatus.WRITE_FAILED, states[-1].status)
            self.assertEqual("same", states[-1].case_id)
            self.assertEqual(first_path.resolve(), states[-1].path)
            panel._auto_load_case_artifact(second_row)
            self.assertEqual([second_path.resolve()], reads)
            self.assertEqual(ArtifactViewStatus.CURRENT, states[-1].status)

            panel._run_rows = ({**first_row, "save_vtp_on": 0},)
            panel._on_run_completed(GuiRunResult())
            panel._auto_load_case_artifact(first_row)
            self.assertEqual([second_path.resolve()], reads)

            panel.load_input_file(root / "changed.csv")
            panel._auto_load_case_artifact(first_row)
            self.assertEqual([second_path.resolve(), first_path.resolve()], reads)

            panel._run_rows = (first_row,)
            with patch.object(QtWidgets.QMessageBox, "warning"):
                panel._on_run_completed(GuiRunResult(output_issues=(issue,)))
            self.assertTrue(panel._invalid_current_vtp_artifacts)
            panel.clear_loaded_cases()
            self.assertEqual(set(), panel._invalid_current_vtp_artifacts)

    def test_validation_failure_clears_prior_state_and_shows_structured_issues(
        self,
    ) -> None:
        panel, _ = self.make_panel()
        panel.load_input_file("/tmp/good.csv")

        def read_invalid(_path):
            raise StructuredError()

        failing_spec = fmf_solver_spec(adapters=_adapters((), {}, reader=read_invalid))
        panel.spec = failing_spec
        with patch.object(ValidationIssuesDialog, "exec", return_value=0) as show:
            self.assertFalse(panel.load_input_file("/tmp/bad.csv"))
        show.assert_called_once()
        self.assertEqual((), panel.case_rows)
        self.assertIsNone(panel.input_path)
        self.assertEqual(0, panel.case_table.rowCount())
        self.assertEqual("Run Cases", panel.btn_run.text())
        self.assertFalse(panel.btn_run.isEnabled())

    def test_run_request_emits_all_or_selected_rows_without_semantic_change(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="run_scope_request_") as directory:
            for selected_row, expected_label, expected_ids in (
                (None, "Run All Cases", ["case_b", "case_a"]),
                (1, "Run Selected Cases", ["case_a"]),
            ):
                with self.subTest(selected_row=selected_row):
                    panel, _ = self.make_panel()
                    panel.load_input_file(Path(directory) / "cases.csv")
                    if selected_row is not None:
                        panel.case_table.selectRow(selected_row)
                    emitted: list[tuple] = []
                    panel.run_requested.connect(
                        lambda *args, sink=emitted: sink.append(args)
                    )

                    with patch.object(
                        QtWidgets.QFileDialog,
                        "getSaveFileName",
                        return_value=(str(Path(directory) / "result.csv"), "CSV"),
                    ):
                        panel.request_run()
                    self.wait_until(
                        lambda active_panel=panel: not active_panel.is_running()
                    )

                    self.assertEqual(expected_label, panel.btn_run.text())
                    self.assertEqual(
                        expected_ids,
                        [row["case_id"] for row in emitted[0][0]],
                    )

    def test_run_request_default_side_effect_selection_and_validation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="phase6_run_") as directory:
            input_path = Path(directory) / "cases.csv"
            captured: dict[str, object] = {}

            def validate(out, source, rows):
                captured["validated"] = (Path(out), Path(source), list(rows))
                return Path(out)

            panel, _ = self.make_panel(validator=validate)
            panel.load_input_file(input_path)
            panel.spin_checkpoint_every_cases.setValue(37)
            emitted: list[tuple] = []
            panel.run_requested.connect(lambda *args: emitted.append(args))

            def choose(_parent, _title, default, _filter):
                captured["default"] = Path(default)
                captured["dir_existed"] = Path(default).parent.exists()
                return (str(Path(directory) / "result.csv"), "CSV")

            with patch.object(
                QtWidgets.QFileDialog, "getSaveFileName", side_effect=choose
            ):
                panel.request_run()
            self.wait_until(lambda: not panel.is_running())
            self.assertEqual(
                Path(directory) / "outputs" / "cases_result.csv",
                captured["default"],
            )
            self.assertTrue(captured["dir_existed"])
            self.assertEqual(
                ["case_b", "case_a"], [r["case_id"] for r in emitted[0][0]]
            )
            self.assertEqual(1, emitted[0][1])
            self.assertEqual(37, emitted[0][2])
            self.assertEqual(Path(directory) / "result.csv", emitted[0][3])

    def test_checkpoint_spinbox_defaults_and_accepts_zero(self) -> None:
        panel, _ = self.make_panel()
        self.assertIsInstance(panel.spin_workers, QtWidgets.QSpinBox)
        self.assertEqual(1, panel.spin_workers.minimum())
        self.assertEqual(os.cpu_count() or 1, panel.spin_workers.maximum())
        self.assertEqual(1, panel.spin_workers.value())
        self.assertIsInstance(
            panel.spin_checkpoint_every_cases,
            QtWidgets.QSpinBox,
        )
        self.assertEqual(
            DEFAULT_CHECKPOINT_CASES,
            panel.spin_checkpoint_every_cases.value(),
        )
        self.assertEqual(0, panel.spin_checkpoint_every_cases.minimum())
        self.assertEqual(
            2_147_483_647,
            panel.spin_checkpoint_every_cases.maximum(),
        )
        self.assertEqual("", panel.spin_checkpoint_every_cases.suffix())
        self.assertEqual("cases", panel.lbl_checkpoint_unit.text())
        self.assertIs(
            panel.spin_checkpoint_every_cases,
            panel.lbl_checkpoint_every_cases.buddy(),
        )
        self.assertEqual(
            QtCore.Qt.FocusPolicy.NoFocus,
            panel.lbl_checkpoint_unit.focusPolicy(),
        )
        self.assertIn(
            "cases",
            panel.spin_checkpoint_every_cases.accessibleDescription(),
        )
        self.assertIn(
            "2147483647",
            panel.spin_checkpoint_every_cases.accessibleDescription(),
        )
        self.assertIn("2,147,483,647", panel.spin_checkpoint_every_cases.toolTip())
        panel.spin_checkpoint_every_cases.setValue(0)
        self.assertEqual(0, panel.spin_checkpoint_every_cases.value())

    def test_checkpoint_spinbox_bounds_ordinary_width_and_keeps_maximum_editable(
        self,
    ) -> None:
        panel, _ = self.make_panel()
        checkpoint = panel.spin_checkpoint_every_cases
        panel.show()
        self.app.processEvents()
        checkpoint.ensurePolished()

        option = QtWidgets.QStyleOptionSpinBox()
        checkpoint.initStyleOption(option)
        edit_field = checkpoint.style().subControlRect(
            QtWidgets.QStyle.ComplexControl.CC_SpinBox,
            option,
            QtWidgets.QStyle.SubControl.SC_SpinBoxEditField,
            checkpoint,
        )
        default_text = checkpoint.text()
        self.assertEqual(str(DEFAULT_CHECKPOINT_CASES), default_text)
        self.assertTrue(panel.lbl_checkpoint_unit.isVisible())
        self.assertGreaterEqual(
            edit_field.width(),
            checkpoint.fontMetrics().horizontalAdvance(default_text),
        )
        self.assertLess(checkpoint.width(), checkpoint.sizeHint().width())

        checkpoint.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
        checkpoint.lineEdit().selectAll()
        QtTest.QTest.keyClicks(checkpoint, "2147483647")
        QtTest.QTest.keyClick(checkpoint, QtCore.Qt.Key.Key_Return)
        self.assertEqual(2_147_483_647, checkpoint.value())
        self.assertEqual("2147483647", checkpoint.text())
        self.assertEqual("2147483647", checkpoint.lineEdit().text())
        panel.close()

    def test_table_and_log_keep_primary_secondary_stretch_contract(self) -> None:
        panel, _ = self.make_panel()
        root = panel.layout()
        self.assertIs(panel.case_table, root.itemAt(2).widget())
        self.assertEqual(4, root.stretch(2))
        self.assertIs(panel.execution_row, root.itemAt(4).layout())
        self.assertIs(panel.progress, panel.execution_row.itemAt(0).widget())
        self.assertIs(panel.btn_diagnostics, root.itemAt(5).widget())
        self.assertIs(panel.log, root.itemAt(6).widget())
        self.assertEqual(
            QtWidgets.QSizePolicy.Policy.Expanding,
            panel.btn_diagnostics.sizePolicy().horizontalPolicy(),
        )
        self.assertEqual(2, root.stretch(6))
        self.assertEqual(180, panel.log.minimumHeight())
        self.assertFalse(panel.progress.isHidden())

    def test_run_cancel_and_output_rejection_do_not_emit(self) -> None:
        def reject(_out, _input, _rows):
            raise ValueError("collision")

        panel, _ = self.make_panel(validator=reject)
        panel.load_input_file("/tmp/cases.csv")
        emitted: list[tuple] = []
        panel.run_requested.connect(lambda *args: emitted.append(args))
        with patch.object(
            QtWidgets.QFileDialog, "getSaveFileName", return_value=("", "")
        ):
            panel.request_run()
        with (
            patch.object(
                QtWidgets.QFileDialog,
                "getSaveFileName",
                return_value=("/tmp/result.csv", "CSV"),
            ),
            patch.object(QtWidgets.QMessageBox, "critical") as critical,
        ):
            panel.request_run()
        self.assertEqual([], emitted)
        critical.assert_called_once()
        self.assertIn("collision", panel.log.toPlainText())


if __name__ == "__main__":
    unittest.main()
