from __future__ import annotations

import csv
import os
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets
from shiboken6 import delete, isValid

from panelsolver.app import sectional_batch, sectional_dialog
from panelsolver.app.cases_panel import CasesPanel
from panelsolver.app.main_window import MainWindow
from panelsolver.app.sectional_batch import SectionalBatchResult
from panelsolver.app.sectional_dialog import SectionalLoadsDialog
from panelsolver.app.solver_spec import GuiRunResult
from panelsolver.domains import fmf, hypersonic
from tests.gui.test_run_lifecycle import _FakeViewer

ROOT = Path(__file__).parents[2]
HEADER = (
    "section_id,origin_x_stl_m,origin_y_stl_m,origin_z_stl_m,"
    "direction_x_stl,direction_y_stl,direction_z_stl,bin_count\n"
)


class SectionalDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="sectional-gui-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.definition_path = self.root / "sections.csv"
        self.definition_path.write_text(
            HEADER + "span,0,0,0,0,1,0,3\noblique,0,0,0,.2,.9,.4,2\n"
        )

    def own(self, widget):
        self.addCleanup(self.dispose, widget)
        return widget

    def dispose(self, widget) -> None:
        if not isValid(widget):
            return
        dialogs = widget.findChildren(SectionalLoadsDialog)
        if isinstance(widget, SectionalLoadsDialog):
            dialogs.append(widget)
        for dialog in dialogs:
            if dialog.is_running():
                dialog.cancel_run()
                self.wait_until(lambda active=dialog: not active.is_running())
        panels = widget.findChildren(CasesPanel)
        if isinstance(widget, CasesPanel):
            panels.append(widget)
        for panel in panels:
            if panel.is_running():
                panel.cancel_run()
                self.wait_until(lambda active=panel: not active.is_running())
        widget.close()
        delete(widget)

    def wait_until(self, predicate, timeout=8.0) -> None:
        deadline = time.monotonic() + timeout
        while not predicate():
            self.app.processEvents()
            if time.monotonic() >= deadline:
                self.fail("timed out waiting for sectional GUI lifecycle")
            time.sleep(0.002)
        self.app.processEvents()

    def test_cp_dialog_runs_and_protects_both_definition_files(self):
        for domain in (fmf, hypersonic):
            with self.subTest(domain=domain.RUNTIME_POLICY.product_id):
                window, panel, loads = self.make_window(domain)
                cp_path = self.root / "cp.csv"
                cp_path.write_text(
                    HEADER.replace("bin_count", "section_count")
                    + "cuts,0,0,0,0,1,0,3\n"
                )
                window.open_sectional_cp()
                cp = window.sectional_cp_dialog
                self.assertTrue(cp.load_definitions(cp_path))
                self.assertIn("planes", cp.definition_model.columns)
                self.assertIn(cp_path, panel.sectional_definition_paths)
                self.assertIn(self.definition_path, panel.sectional_definition_paths)
                output = self.root / "cp-result.csv"
                self.assertTrue(cp.start_run(output))
                self.assertFalse(loads.start_run(self.root / "loads.csv"))
                self.assertFalse(loads.load_definitions(self.definition_path))
                self.wait_until(lambda current=cp: not current.is_running())
                self.assertTrue(output.exists())
                self.assertEqual(cp.batch_result.status, "completed")
                with output.open(encoding="utf-8-sig") as stream:
                    rows = list(csv.DictReader(stream))
                self.assertIn("x0_stl_m", rows[0])
                self.assertTrue(loads.btn_run.isEnabled())

    def make_window(self, domain=fmf, *, runner=None, normal_runner=None):
        spec = domain.gui_spec()
        if runner is not None:
            spec = replace(
                spec, adapters=replace(spec.adapters, run_sectional_cases=runner)
            )
        if normal_runner is not None:
            spec = replace(
                spec, adapters=replace(spec.adapters, run_cases=normal_runner)
            )
        panel = self.own(CasesPanel(spec))
        source = (
            domain.read_cases(
                ROOT / "examples" / domain.RUNTIME_POLICY.product_id / "basic.csv"
            )
            .iloc[0]
            .to_dict()
        )
        rows = tuple(
            {**source, "case_id": f"case_{i}", "out_dir": str(self.root / "unused")}
            for i in range(2)
        )
        panel.case_rows = rows
        panel.input_path = self.root / "cases.csv"
        panel.input_path.write_text("original case input")
        panel._populate_case_table()
        panel._set_running_state(False)
        window = self.own(
            MainWindow(
                spec,
                cases_panel=panel,
                viewer_panel=_FakeViewer(),
                persist_layout=False,
            )
        )
        window.open_sectional_loads()
        dialog = window.sectional_dialog
        self.assertTrue(dialog.load_definitions(self.definition_path))
        return window, panel, dialog

    @staticmethod
    def select(table, *indices) -> None:
        selection = table.selectionModel()
        selection.clearSelection()
        for index in indices:
            selection.select(
                table.model().index(index, 0),
                QtCore.QItemSelectionModel.SelectionFlag.Select
                | QtCore.QItemSelectionModel.SelectionFlag.Rows,
            )

    def test_cp_example_replaces_cases_loads_definitions_and_runs_both_domains(self):
        for domain in (fmf, hypersonic):
            with self.subTest(domain=domain.RUNTIME_POLICY.product_id):
                window, panel, loads_dialog = self.make_window(domain)
                loads_dialog.close()
                destination = self.root / domain.RUNTIME_POLICY.product_id
                action = next(
                    a for a in window.example_actions if a.text() == "Sectional Cp"
                )
                self.assertTrue(action.isEnabled())
                original_input = panel.input_path
                with patch.object(
                    QtWidgets.QFileDialog, "getExistingDirectory", return_value=""
                ):
                    action.trigger()
                self.assertEqual(original_input, panel.input_path)
                self.assertIsNone(window.sectional_cp_dialog)
                with patch.object(
                    QtWidgets.QFileDialog,
                    "getExistingDirectory",
                    return_value=str(destination),
                ):
                    action.trigger()
                dialog = window.sectional_cp_dialog
                self.assertTrue(dialog.cp)
                self.assertTrue(dialog.isVisible())
                self.assertFalse(loads_dialog.isVisible())
                self.assertTrue(panel.input_path.is_relative_to(destination.resolve()))
                self.assertEqual(
                    destination.resolve() / "sectional_cp.csv", dialog.definition_path
                )
                self.assertEqual(
                    ["span", "center"], [d.section_id for d in dialog.definitions]
                )
                self.assertIsNone(dialog.batch_result)
                self.assertTrue(dialog.btn_run.isEnabled())
                target = destination / "cp.csv"
                self.assertTrue(dialog.start_run(target))
                self.wait_until(lambda dialog=dialog: not dialog.is_running())
                self.assertEqual("completed", dialog.batch_result.status)
                self.assertEqual(
                    len(panel.case_rows) * 2, dialog.batch_result.completed_pairs
                )
                with target.open(encoding="utf-8-sig") as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual(
                    {"normal_traction_coeff" if domain is fmf else "cp"},
                    {row["scalar_name"] for row in rows},
                )

    def test_sectional_example_copies_loads_and_runs_both_domains(self):
        for domain in (fmf, hypersonic):
            with self.subTest(domain=domain.RUNTIME_POLICY.product_id):
                window, panel, dialog = self.make_window(domain)
                dialog.close()
                destination = self.root / domain.RUNTIME_POLICY.product_id
                action = next(
                    a for a in window.example_actions if a.text() == "Sectional Loads"
                )
                with patch.object(
                    QtWidgets.QFileDialog,
                    "getExistingDirectory",
                    return_value=str(destination),
                ):
                    action.trigger()
                self.assertTrue(dialog.isVisible())
                self.assertTrue(panel.input_path.is_relative_to(destination.resolve()))
                self.assertEqual(
                    destination.resolve() / "sectional_loads.csv",
                    dialog.definition_path,
                )
                self.assertEqual(
                    ["span", "oblique", "partial"],
                    [d.section_id for d in dialog.definitions],
                )
                self.assertTrue(dialog.btn_run.isEnabled())
                self.assertTrue(dialog.start_run(destination / "result.csv"))
                self.wait_until(lambda dialog=dialog: not dialog.is_running())
                self.assertEqual("completed", dialog.batch_result.status)
                self.assertEqual(
                    len(panel.case_rows) * 3, dialog.batch_result.completed_pairs
                )
                self.assertTrue((destination / "result.csv").is_file())
                original = dialog.definition_path.read_bytes()
                with (
                    patch.object(
                        QtWidgets.QFileDialog,
                        "getSaveFileName",
                        return_value=(str(dialog.definition_path), ""),
                    ),
                    patch.object(QtWidgets.QMessageBox, "critical") as error,
                ):
                    panel.request_run()
                error.assert_called_once()
                self.assertEqual(original, dialog.definition_path.read_bytes())

    def test_sectional_example_cancel_and_collision_preserve_loaded_inputs(self):
        window, panel, dialog = self.make_window()
        action = next(
            a for a in window.example_actions if a.text() == "Sectional Loads"
        )
        previous = (
            panel.input_path,
            panel.case_rows,
            dialog.definition_path,
            dialog.definitions,
        )
        with (
            patch.object(
                QtWidgets.QFileDialog, "getExistingDirectory", return_value=""
            ),
            patch.object(window._example_library, "copy_example") as copy,
        ):
            action.trigger()
        copy.assert_not_called()
        destination = self.root / "collision"
        destination.mkdir()
        definition = destination / "sectional_loads.csv"
        definition.write_text("user-edited definitions")
        with (
            patch.object(
                QtWidgets.QFileDialog,
                "getExistingDirectory",
                return_value=str(destination),
            ),
            patch.object(QtWidgets.QMessageBox, "critical") as error,
        ):
            action.trigger()
        error.assert_called_once()
        self.assertEqual("user-edited definitions", definition.read_text())
        self.assertEqual(
            previous,
            (
                panel.input_path,
                panel.case_rows,
                dialog.definition_path,
                dialog.definitions,
            ),
        )
        self.assertFalse((destination / "fmf").exists())

    def test_sectional_example_blocked_during_calculation(self):
        window, panel, dialog = self.make_window()
        action = next(
            a for a in window.example_actions if a.text() == "Sectional Loads"
        )
        for owner in (panel, dialog):
            with (
                patch.object(owner, "is_running", return_value=True),
                patch.object(QtWidgets.QFileDialog, "getExistingDirectory") as picker,
            ):
                action.trigger()
            picker.assert_not_called()

    def test_read_only_open_reload_and_default_all_selection(self):
        window, panel, dialog = self.make_window()
        self.assertTrue(dialog.btn_run.isEnabled())
        self.assertEqual(dialog.definitions, dialog.selected_or_all_definitions())
        self.assertTrue(dialog.btn_retry_save.isHidden())
        self.assertFalse(
            any(
                "Export" in button.text()
                for button in dialog.findChildren(QtWidgets.QPushButton)
            )
        )
        self.assertEqual(2, dialog.definition_model.rowCount())
        index = dialog.definition_model.index(0, 0)
        self.assertFalse(
            dialog.definition_model.flags(index) & QtCore.Qt.ItemFlag.ItemIsEditable
        )
        self.assertFalse(dialog.definition_model.setData(index, "changed"))
        self.assertEqual("span", dialog.definitions[0].section_id)
        self.select(panel.case_table, 1)
        self.assertTrue(dialog.btn_run.isEnabled())
        self.select(dialog.definition_table, 0)
        self.assertTrue(dialog.btn_run.isEnabled())
        panel.spin_workers.setRange(1, 2)
        panel.spin_workers.setValue(2)
        self.assertIn("Workers: 2", dialog.selection_status.text())
        panel.spin_workers.setValue(1)
        self.assertIn("Workers: 1", dialog.selection_status.text())
        self.definition_path.write_text(HEADER + "reloaded,0,0,0,0,1,0,4\n")
        dialog.reload_definitions()
        self.assertEqual(
            ("reloaded",), tuple(item.section_id for item in dialog.definitions)
        )
        self.assertTrue(dialog.btn_run.isEnabled())
        self.assertEqual(dialog.definitions, dialog.selected_or_all_definitions())
        self.select(dialog.definition_table, 0)
        self.definition_path.write_text(HEADER + "broken,0,0,0,0,0,0,4\n")
        dialog.reload_definitions()
        self.assertEqual((), dialog.definitions)
        self.assertIn("read failed", dialog.definition_status.text())
        self.assertFalse(dialog.start_run(self.root / "automatic.csv"))
        self.assertFalse(dialog.btn_run.isEnabled())
        self.assertEqual(str(self.definition_path), dialog.path_value.text())
        window.open_sectional_loads()
        self.assertIs(window.sectional_dialog, dialog)

    def test_normal_run_rejects_loaded_definition_output(self):
        for domain in (fmf, hypersonic):
            with self.subTest(domain=domain.RUNTIME_POLICY.product_id):
                _window, panel, dialog = self.make_window(domain)
                dialog.close()
                original = self.definition_path.read_bytes()
                with (
                    patch.object(
                        QtWidgets.QFileDialog,
                        "getSaveFileName",
                        return_value=(str(self.definition_path), "CSV (*.csv)"),
                    ),
                    patch.object(QtWidgets.QMessageBox, "critical") as error,
                    patch.object(panel, "start_run") as start,
                ):
                    panel.request_run()
                start.assert_not_called()
                error.assert_called_once()
                self.assertEqual(original, self.definition_path.read_bytes())

    def test_normal_output_protection_tracks_reload_and_loaded_symlink_target(self):
        _window, panel, dialog = self.make_window()
        source = self.root / "source.csv"
        source.symlink_to(self.definition_path)
        self.assertTrue(dialog.load_definitions(source))
        replacement = self.root / "replacement.csv"
        replacement.write_bytes(self.definition_path.read_bytes())
        source.unlink()
        source.symlink_to(replacement)
        alias = self.root / "alias.csv"
        alias.hardlink_to(self.definition_path)
        for output in (self.definition_path, source, replacement, alias):
            with self.subTest(output=output.name):
                original = output.read_bytes()
                with (
                    patch.object(
                        QtWidgets.QFileDialog,
                        "getSaveFileName",
                        return_value=(str(output), "CSV (*.csv)"),
                    ),
                    patch.object(QtWidgets.QMessageBox, "critical") as error,
                    patch.object(panel, "start_run") as start,
                ):
                    panel.request_run()
                start.assert_not_called()
                error.assert_called_once()
                self.assertEqual(original, output.read_bytes())
        replacement.write_text("invalid definition")
        dialog.reload_definitions()
        with (
            patch.object(
                QtWidgets.QFileDialog,
                "getSaveFileName",
                return_value=(str(replacement), "CSV (*.csv)"),
            ),
            patch.object(QtWidgets.QMessageBox, "critical") as error,
            patch.object(panel, "start_run") as start,
        ):
            panel.request_run()
        start.assert_not_called()
        error.assert_called_once()
        self.assertTrue(dialog.load_definitions(self.definition_path))
        with (
            patch.object(
                QtWidgets.QFileDialog,
                "getSaveFileName",
                return_value=(str(replacement), "CSV (*.csv)"),
            ),
            patch.object(QtWidgets.QMessageBox, "critical") as error,
            patch.object(panel, "start_run") as start,
        ):
            panel.request_run()
        start.assert_called_once()
        error.assert_not_called()

    def test_real_both_domain_runs_match_service_and_solve_once_per_case(self):
        for domain in (fmf, hypersonic):
            with self.subTest(domain=domain.RUNTIME_POLICY.product_id):
                _window, panel, dialog = self.make_window(domain)
                self.select(panel.case_table, 0, 1)
                self.select(dialog.definition_table, 0, 1)
                expected = sectional_batch.run_sectional_cases(
                    panel.case_rows, domain.RUNTIME_POLICY, dialog.definitions
                )
                gui_thread = threading.get_ident()
                observed_threads = []
                original = sectional_batch.execute_case

                def record(
                    *args, observed=observed_threads, execute=original, **kwargs
                ):
                    observed.append(threading.get_ident())
                    return execute(*args, **kwargs)

                with patch.object(
                    sectional_batch, "execute_case", side_effect=record
                ) as execute:
                    self.assertTrue(dialog.start_run(self.root / "automatic.csv"))
                    self.wait_until(lambda dialog=dialog: not dialog.is_running())
                self.assertEqual(2, execute.call_count)
                self.assertTrue(
                    all(thread != gui_thread for thread in observed_threads)
                )
                self.assertEqual(expected, dialog.batch_result)
                self.assertIn(
                    "Saved completed snapshot (4/4 pairs)", dialog.result_status.text()
                )
                self.assertIn("automatic.csv", dialog.result_status.text())
                self.assertEqual("Saved (completed)", dialog.progress.text())
                self.assertTrue(dialog.btn_retry_save.isHidden())
                self.assertFalse((self.root / "unused").exists())
                output = self.root / f"{domain.RUNTIME_POLICY.product_id}.csv"
                self.assertTrue(dialog._save_results(output))
                self.wait_until(lambda dialog=dialog: not dialog.is_running())
                with output.open(encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual(20, len(rows))
                self.assertEqual({"case_0", "case_1"}, {row["case_id"] for row in rows})

    def test_run_button_chooses_output_and_runs_selected_or_all_cases_and_definitions(
        self,
    ):
        _window, panel, dialog = self.make_window()
        for selected, sections, expected, expected_sections in (
            ((), (), ["case_0", "case_1"], ["span", "oblique"]),
            ((1,), (), ["case_1"], ["span", "oblique"]),
            ((), (1,), ["case_0", "case_1"], ["oblique"]),
            ((1,), (0,), ["case_1"], ["span"]),
        ):
            with self.subTest(selected=selected, sections=sections):
                self.select(panel.case_table, *selected)
                self.select(dialog.definition_table, *sections)
                self.assertIn(
                    "selected" if selected else "all loaded",
                    dialog.selection_status.text(),
                )
                self.assertIn("Selected" if selected else "All", dialog.btn_run.text())
                output = self.root / f"selection-{len(selected)}.csv"
                with (
                    patch.object(
                        QtWidgets.QFileDialog,
                        "getSaveFileName",
                        return_value=(str(output), "CSV (*.csv)"),
                    ) as picker,
                    patch.object(
                        sectional_batch,
                        "execute_case",
                        wraps=sectional_batch.execute_case,
                    ) as execute,
                ):
                    dialog.btn_run.click()
                    self.wait_until(lambda dialog=dialog: not dialog.is_running())
                picker.assert_called_once()
                self.assertEqual(len(expected), execute.call_count)
                self.assertEqual(
                    str(self.root / "outputs/cases_sectional_loads.csv"),
                    picker.call_args.args[2],
                )
                with output.open(encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                    self.assertEqual(
                        expected,
                        list(dict.fromkeys(row["case_id"] for row in rows)),
                    )
                    self.assertEqual(
                        expected_sections,
                        list(dict.fromkeys(row["section_id"] for row in rows)),
                    )
                self.assertTrue(dialog.btn_retry_save.isHidden())

    def test_output_picker_cancel_preserves_previous_result_without_solving(self):
        _window, _panel, dialog = self.make_window()
        self.select(dialog.definition_table, 0)
        output = self.root / "previous.csv"
        self.assertTrue(dialog.start_run(output))
        self.wait_until(lambda: not dialog.is_running())
        retained, status, contents = (
            dialog.batch_result,
            dialog.result_status.text(),
            output.read_bytes(),
        )
        with (
            patch.object(
                QtWidgets.QFileDialog, "getSaveFileName", return_value=("", "")
            ),
            patch.object(sectional_batch, "execute_case") as execute,
        ):
            dialog.btn_run.click()
        execute.assert_not_called()
        self.assertFalse(dialog.is_running())
        self.assertIs(retained, dialog.batch_result)
        self.assertEqual(status, dialog.result_status.text())
        self.assertEqual(contents, output.read_bytes())

    def test_run_rejects_protected_output_before_solving(self):
        _window, panel, dialog = self.make_window()
        self.select(dialog.definition_table, 0)
        self.select(panel.case_table, 0)
        unselected_stl = self.root / "unselected.stl"
        unselected_stl.write_bytes((ROOT / "examples/geometry/plate.stl").read_bytes())
        panel.case_rows[1]["stl_path"] = str(unselected_stl)
        with patch.object(sectional_batch, "execute_case") as execute:
            for path in (panel.input_path, self.definition_path, unselected_stl):
                contents = path.read_bytes()
                self.assertFalse(dialog.start_run(path))
                self.assertIn("Invalid output path", dialog.result_status.text())
                self.assertEqual(contents, path.read_bytes())
        execute.assert_not_called()
        self.assertFalse(panel._external_run_active)

    def test_failed_or_empty_run_never_autosaves_previous_result(self):
        outcomes = []

        def runner(request):
            if outcomes:
                outcome = outcomes.pop(0)
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
            return fmf.GUI_ADAPTERS.run_sectional_cases(request)

        _window, _panel, dialog = self.make_window(runner=runner)
        self.select(dialog.definition_table, 0)
        self.assertTrue(dialog.start_run(self.root / "previous.csv"))
        self.wait_until(lambda: not dialog.is_running())
        retained = dialog.batch_result
        output = self.root / "next.csv"
        output.write_text("existing valid output")
        for outcome in (
            RuntimeError("calculation failed"),
            SectionalBatchResult(None, "cancelled", 0, 2, 0, 2),
        ):
            outcomes.append(outcome)
            self.assertTrue(dialog.start_run(output))
            self.wait_until(lambda: not dialog.is_running())
            self.assertEqual("existing valid output", output.read_text())
            if isinstance(outcome, Exception):
                self.assertIs(retained, dialog.batch_result)
                self.assertIn("Calculation failed", dialog.result_status.text())
            else:
                self.assertIsNone(dialog.batch_result.csv)
                self.assertIn("Cancelled", dialog.result_status.text())

    def test_automatic_save_failure_retains_result_for_export_without_resolve(self):
        _window, panel, dialog = self.make_window()
        self.select(dialog.definition_table, 0)
        output = self.root / "automatic.csv"
        output.write_text("old valid output")
        with patch(
            "panelsolver.app.csv_writer.os.replace", side_effect=OSError("disk full")
        ):
            self.assertTrue(dialog.start_run(output))
            self.wait_until(lambda: not dialog.is_running())
        self.assertIn("Save failed", dialog.result_status.text())
        self.assertEqual("old valid output", output.read_text())
        self.assertFalse(panel._external_run_active)
        retained = dialog.batch_result
        self.assertFalse(dialog.btn_retry_save.isHidden())
        self.assertTrue(dialog.btn_retry_save.isEnabled())
        with patch.object(
            sectional_batch, "execute_case", side_effect=AssertionError("resolve")
        ):
            with patch.object(
                QtWidgets.QFileDialog,
                "getSaveFileName",
                return_value=(str(output), "CSV (*.csv)"),
            ):
                dialog.btn_retry_save.click()
                self.wait_until(lambda: not dialog.is_running())
        self.assertIs(retained, dialog.batch_result)
        self.assertIn("Saved completed", dialog.result_status.text())
        self.assertTrue(dialog.btn_retry_save.isHidden())

    def test_failed_partial_run_automatically_saves_only_successful_pairs(self):
        _window, _panel, dialog = self.make_window()
        self.definition_path.write_text(
            HEADER.rstrip("\n") + ",component_ids\n"
            "valid,0,0,0,0,1,0,3,0\nunknown,0,0,0,0,1,0,3,999\n"
        )
        dialog.reload_definitions()
        self.select(dialog.definition_table, 0, 1)
        output = self.root / "partial.csv"
        self.assertTrue(dialog.start_run(output))
        self.wait_until(lambda: not dialog.is_running())
        self.assertEqual("failed", dialog.batch_result.status)
        with output.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual({"failed"}, {row["batch_status"] for row in rows})
        self.assertEqual(
            {("case_0", "valid")}, {(row["case_id"], row["section_id"]) for row in rows}
        )
        self.assertIn("Saved failed snapshot", dialog.result_status.text())

    def test_retry_after_reload_and_new_calculation_failure_keeps_old_snapshot(self):
        _window, panel, dialog = self.make_window()
        self.select(panel.case_table, 0)
        self.select(dialog.definition_table, 0)
        old_output = self.root / "unsaved.csv"
        with patch.object(
            sectional_dialog, "write_sectional_csv", side_effect=OSError("disk full")
        ):
            self.assertTrue(dialog.start_run(old_output))
            self.wait_until(lambda: not dialog.is_running())
        retained = dialog.batch_result
        self.definition_path.write_text("invalid header\n")
        dialog.reload_definitions()
        self.assertFalse(dialog.btn_run.isEnabled())
        self.assertTrue(dialog.btn_retry_save.isEnabled())
        self.definition_path.write_text(HEADER + "new-label,0,0,0,0,1,0,4\n")
        dialog.reload_definitions()
        self.select(panel.case_table, 1)
        new_output = self.root / "new-run.csv"
        with patch.object(
            dialog, "_runner", side_effect=RuntimeError("new calculation failed")
        ):
            self.assertTrue(dialog.start_run(new_output))
            self.wait_until(lambda: not dialog.is_running())
        self.assertIs(retained, dialog.batch_result)
        self.assertTrue(dialog.btn_retry_save.isEnabled())
        with patch.object(
            QtWidgets.QFileDialog, "getSaveFileName", return_value=("", "")
        ) as picker:
            dialog.btn_retry_save.click()
        self.assertEqual(str(old_output.resolve()), picker.call_args.args[2])
        self.assertTrue(dialog.btn_retry_save.isEnabled())
        self.assertFalse(dialog.is_running())
        output = self.root / "retried.csv"
        with (
            patch.object(
                QtWidgets.QFileDialog,
                "getSaveFileName",
                return_value=(str(output), "CSV (*.csv)"),
            ),
            patch.object(
                sectional_batch,
                "execute_case",
                side_effect=AssertionError("recalculation"),
            ),
        ):
            dialog.btn_retry_save.click()
            self.wait_until(lambda: not dialog.is_running())
        with output.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(
            {("case_0", "span")}, {(row["case_id"], row["section_id"]) for row in rows}
        )
        self.assertFalse(new_output.exists())
        self.assertTrue(dialog.btn_retry_save.isHidden())

    def test_new_empty_result_clears_previous_save_retry(self):
        _window, _panel, dialog = self.make_window()
        with patch.object(
            sectional_dialog, "write_sectional_csv", side_effect=OSError("disk full")
        ):
            self.assertTrue(dialog.start_run(self.root / "unsaved.csv"))
            self.wait_until(lambda: not dialog.is_running())
        self.assertTrue(dialog.btn_retry_save.isEnabled())
        with patch.object(
            dialog,
            "_runner",
            return_value=SectionalBatchResult(None, "cancelled", 0, 4, 0, 2),
        ):
            self.assertTrue(dialog.start_run(self.root / "empty.csv"))
            self.wait_until(lambda: not dialog.is_running())
        self.assertTrue(dialog.btn_retry_save.isHidden())
        self.assertFalse(dialog.retry_save())
        self.assertIsNone(dialog.batch_result.csv)

    def test_protected_path_resolution_failure_releases_run_guard(self):
        link = self.root / "definition-link.csv"
        link.symlink_to(self.definition_path)
        real_runner = fmf.GUI_ADAPTERS.run_sectional_cases

        def runner(request):
            result = real_runner(request)
            link.unlink()
            link.symlink_to(link.name)
            return result

        _window, panel, dialog = self.make_window(runner=runner)
        self.assertTrue(dialog.load_definitions(link))
        self.select(dialog.definition_table, 0)
        finished = []
        dialog.run_finished.connect(lambda: finished.append(True))
        output = self.root / "result.csv"
        self.assertTrue(dialog.start_run(output))
        self.wait_until(lambda: not dialog.is_running())
        self.assertIn("Save failed", dialog.result_status.text())
        self.assertFalse(panel._external_run_active)
        self.assertEqual([True], finished)
        self.assertFalse(output.exists())
        retained = dialog.batch_result
        self.assertFalse(dialog.start_run(output))
        self.assertIn("Invalid output path", dialog.result_status.text())
        link.unlink()
        link.symlink_to(self.definition_path)
        self.assertTrue(dialog._save_results(output))
        self.wait_until(lambda: not dialog.is_running())
        self.assertIs(retained, dialog.batch_result)
        self.assertTrue(output.exists())

    def test_close_during_automatic_save_failure_keeps_result_for_retry(self):
        for route in ("dialog", "main"):
            with self.subTest(route=route):
                window, panel, dialog = self.make_window()
                window.show()
                self.select(dialog.definition_table, 0)
                entered, release = threading.Event(), threading.Event()
                self.addCleanup(release.set)

                def writer(*args, entered=entered, release=release):
                    entered.set()
                    release.wait(5)
                    raise OSError("disk full")

                output = self.root / f"{route}.csv"
                with patch.object(
                    sectional_dialog, "write_sectional_csv", side_effect=writer
                ):
                    self.assertTrue(dialog.start_run(output))
                    self.wait_until(entered.is_set)
                    (dialog if route == "dialog" else window).close()
                    release.set()
                    self.wait_until(lambda dialog=dialog: not dialog.is_running())
                self.assertTrue(window.isVisible())
                self.assertTrue(dialog.isVisible())
                self.assertIn("Save failed", dialog.result_status.text())
                self.assertFalse(panel._external_run_active)
                with patch.object(
                    sectional_batch,
                    "execute_case",
                    side_effect=AssertionError("resolve"),
                ):
                    self.assertTrue(dialog._save_results(output))
                    self.wait_until(lambda dialog=dialog: not dialog.is_running())
                self.assertTrue(output.exists())

    def test_active_snapshot_reload_selection_and_duplicate_run_guards(self):
        entered, release = threading.Event(), threading.Event()
        captured = {}
        real_runner = fmf.GUI_ADAPTERS.run_sectional_cases

        def runner(request):
            captured["request"] = request
            entered.set()
            release.wait(5)
            return real_runner(request)

        _window, panel, dialog = self.make_window(runner=runner)
        self.addCleanup(release.set)
        self.select(panel.case_table, 1)
        self.select(dialog.definition_table, 0)
        self.assertTrue(dialog.start_run(self.root / "automatic.csv"))
        self.wait_until(entered.is_set)
        self.assertFalse(panel.btn_reload_input.isEnabled())
        with patch.object(panel, "load_input_file") as reader:
            panel.btn_reload_input.click()
        reader.assert_not_called()
        self.assertFalse(dialog.start_run(self.root / "automatic.csv"))
        self.assertFalse(
            panel.start_run(panel.case_rows, 1, 0, self.root / "normal.csv")
        )
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName") as picker:
            panel.request_run()
        picker.assert_not_called()
        self.assertFalse(panel.load_input_file(self.root / "different.csv"))
        self.definition_path.write_text(HEADER + "externally_changed,0,0,0,0,1,0,9\n")
        self.assertFalse(dialog.load_definitions(self.definition_path))
        panel.case_rows[1]["case_id"] = "mutated"
        self.select(panel.case_table, 0)
        release.set()
        self.wait_until(lambda: not dialog.is_running())
        self.assertTrue(panel.btn_reload_input.isEnabled())
        request = captured["request"]
        self.assertEqual("case_1", request.rows[0]["case_id"])
        self.assertEqual("span", request.definitions[0].section_id)
        with self.assertRaises(TypeError):
            request.rows[0]["case_id"] = "cannot mutate"
        self.assertEqual(
            {"case_1"}, {row["case_id"] for row in dialog.batch_result.csv.rows}
        )
        self.assertEqual(
            {"span"}, {row["section_id"] for row in dialog.batch_result.csv.rows}
        )
        dialog.reload_definitions()
        self.select(dialog.definition_table, 0)
        output = self.root / "snapshot.csv"
        self.assertTrue(dialog._save_results(output))
        self.wait_until(lambda: not dialog.is_running())
        with output.open(encoding="utf-8-sig", newline="") as handle:
            self.assertEqual(
                {"span"}, {row["section_id"] for row in csv.DictReader(handle)}
            )

    def test_normal_solve_blocks_sectional_until_cleanup(self):
        entered, release = threading.Event(), threading.Event()

        def normal_runner(request):
            entered.set()
            release.wait(5)
            return GuiRunResult()

        _window, panel, dialog = self.make_window(normal_runner=normal_runner)
        self.addCleanup(release.set)
        self.select(panel.case_table, 0)
        self.select(dialog.definition_table, 0)
        self.assertTrue(dialog.start_run(self.root / "automatic.csv"))
        self.wait_until(lambda: not dialog.is_running())
        self.assertTrue(
            panel.start_run(panel.case_rows, 1, 0, self.root / "normal.csv")
        )
        self.assertFalse(dialog.btn_run.isEnabled())
        self.assertFalse(dialog.btn_retry_save.isEnabled())
        self.assertFalse(dialog.btn_open.isEnabled())
        self.assertFalse(dialog.btn_reload.isEnabled())
        previous = dialog.definitions
        candidate = self.root / "during-normal.csv"
        candidate.write_bytes(self.definition_path.read_bytes())
        self.assertFalse(dialog.load_definitions(candidate))
        self.assertEqual(self.definition_path, dialog.definition_path)
        self.assertIs(previous, dialog.definitions)
        self.assertFalse(dialog.start_run(self.root / "automatic.csv"))
        self.assertFalse(dialog._save_results(self.root / "normal.csv"))
        self.wait_until(entered.is_set)
        release.set()
        self.wait_until(lambda: not panel.is_running())
        self.assertTrue(dialog.btn_run.isEnabled())
        self.assertTrue(dialog.btn_open.isEnabled())
        self.assertTrue(dialog.btn_reload.isEnabled())
        self.assertTrue(dialog.load_definitions(candidate))

    def test_cancellation_keeps_partial_result_and_export_failure_is_retryable(self):
        entered = threading.Event()

        def runner(request):
            entered.set()
            while not request.cancel_requested():
                time.sleep(0.002)
            first = sectional_batch.run_sectional_cases(
                request.rows[:1], fmf.RUNTIME_POLICY, request.definitions[:1]
            )
            rows = tuple(dict(row, batch_status="cancelled") for row in first.csv.rows)
            return SectionalBatchResult(
                type(first.csv)(first.csv.columns, rows), "cancelled", 1, 4, 0, 2
            )

        _window, panel, dialog = self.make_window(runner=runner)
        self.select(panel.case_table, 0, 1)
        self.select(dialog.definition_table, 0, 1)
        self.assertTrue(dialog.start_run(self.root / "automatic.csv"))
        self.wait_until(entered.is_set)
        dialog.cancel_run()
        self.assertIn("Cancelling", dialog.progress.text())
        self.wait_until(lambda: not dialog.is_running())
        self.assertEqual("cancelled", dialog.batch_result.status)
        self.assertIn("Saved cancelled snapshot (1/4", dialog.result_status.text())
        with (self.root / "automatic.csv").open(
            encoding="utf-8-sig", newline=""
        ) as handle:
            automatic_rows = list(csv.DictReader(handle))
        self.assertEqual({"cancelled"}, {row["batch_status"] for row in automatic_rows})
        self.assertEqual({"case_0"}, {row["case_id"] for row in automatic_rows})
        retained = dialog.batch_result
        output = self.root / "result.csv"
        output.write_text("old valid contents")
        with patch(
            "panelsolver.app.csv_writer.os.replace", side_effect=OSError("disk failure")
        ):
            self.assertTrue(dialog._save_results(output))
            self.wait_until(lambda: not dialog.is_running())
        self.assertIs(retained, dialog.batch_result)
        self.assertIn("Save failed", dialog.result_status.text())
        self.assertEqual("old valid contents", output.read_text())
        with patch.object(
            sectional_batch, "execute_case", side_effect=AssertionError("recalculation")
        ):
            self.assertTrue(dialog._save_results(output))
            self.wait_until(lambda: not dialog.is_running())
        self.assertIn("cancelled", dialog.result_status.text())
        self.assertEqual("warning", dialog.progress.property("fluentStatus"))

    def test_dialog_escape_and_main_close_wait_for_worker_cleanup(self):
        for route in ("close", "escape", "main"):
            with self.subTest(route=route):
                entered, release = threading.Event(), threading.Event()

                def runner(request, entered=entered, release=release):
                    entered.set()
                    while not request.cancel_requested():
                        time.sleep(0.002)
                    release.wait(5)
                    return SectionalBatchResult(None, "cancelled", 0, 1, 0, 1)

                window, panel, dialog = self.make_window(runner=runner)
                self.addCleanup(release.set)
                window.show()
                self.select(panel.case_table, 0)
                self.select(dialog.definition_table, 0)
                self.assertTrue(dialog.start_run(self.root / "automatic.csv"))
                self.wait_until(entered.is_set)
                if route == "escape":
                    dialog.reject()
                else:
                    target = window if route == "main" else dialog
                    event = QtGui.QCloseEvent()
                    target.closeEvent(event)
                    self.assertFalse(event.isAccepted())
                self.assertTrue(dialog.is_running())
                self.assertTrue(dialog.isVisible())
                self.assertFalse(panel.btn_run.isEnabled())
                release.set()
                self.wait_until(lambda dialog=dialog: not dialog.is_running())
                closing = window if route == "main" else dialog
                self.wait_until(lambda closing=closing: not closing.isVisible())
                self.assertFalse(panel._external_run_active)
                if route == "main":
                    self.assertFalse(dialog.isVisible())

    def test_idle_main_close_hides_persistent_dialog(self):
        window, _panel, dialog = self.make_window()
        window.show()
        self.assertTrue(dialog.isVisible())
        window.close()
        self.app.processEvents()
        self.assertFalse(window.isVisible())
        self.assertFalse(dialog.isVisible())

    def test_old_result_export_protects_new_current_inputs(self):
        _window, panel, dialog = self.make_window()
        self.select(panel.case_table, 0)
        self.select(dialog.definition_table, 0)
        self.assertTrue(dialog.start_run(self.root / "automatic.csv"))
        self.wait_until(lambda: not dialog.is_running())
        retained = dialog.batch_result
        new_definition = self.root / "new-sections.csv"
        new_definition.write_text(HEADER + "new-label,0,0,0,0,1,0,2\n")
        self.assertTrue(dialog.load_definitions(new_definition))
        new_case_file = self.root / "new-cases.csv"
        new_stl = self.root / "new-model.stl"
        new_stl.write_bytes((ROOT / "examples/geometry/plate.stl").read_bytes())
        with new_case_file.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=tuple(panel.case_rows[0]))
            writer.writeheader()
            writer.writerow(dict(panel.case_rows[0], stl_path=str(new_stl)))
        self.assertTrue(panel.load_input_file(new_case_file))
        for path in (new_definition, new_case_file, new_stl):
            original = path.read_bytes()
            self.assertTrue(dialog._save_results(path))
            self.wait_until(lambda: not dialog.is_running())
            self.assertIn("Save failed", dialog.result_status.text())
            self.assertEqual(original, path.read_bytes())
            self.assertIs(retained, dialog.batch_result)
        self.assertTrue(dialog._save_results(self.root / "old-snapshot.csv"))
        self.wait_until(lambda: not dialog.is_running())
        self.assertEqual(
            {"span"}, {row["section_id"] for row in dialog.batch_result.csv.rows}
        )

    def test_path_protection_uses_loaded_definition_target_and_original_result(self):
        _window, panel, dialog = self.make_window()
        source = self.root / "source.csv"
        source.symlink_to(self.definition_path)
        self.assertTrue(dialog.load_definitions(source))
        replacement = self.root / "replacement.csv"
        replacement.write_text(self.definition_path.read_text())
        source.unlink()
        source.symlink_to(replacement)
        self.select(panel.case_table, 0)
        self.select(dialog.definition_table, 0)
        self.assertTrue(dialog.start_run(self.root / "automatic.csv"))
        self.wait_until(lambda: not dialog.is_running())
        for path in (self.definition_path, replacement, panel.input_path):
            original = path.read_bytes()
            self.assertTrue(dialog._save_results(path))
            self.wait_until(lambda: not dialog.is_running())
            self.assertIn("Save failed", dialog.result_status.text())
            self.assertEqual(original, path.read_bytes())

    def test_case_table_symlink_retaining_source_before_run(self):
        _window, panel, dialog = self.make_window()
        original = self.root / "original-cases.csv"
        replacement = self.root / "replacement-cases.csv"
        with original.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=tuple(panel.case_rows[0]))
            writer.writeheader()
            writer.writerows(panel.case_rows)
        replacement.write_bytes(original.read_bytes())
        link = self.root / "case-link.csv"
        link.symlink_to(original)
        self.assertTrue(panel.load_input_file(link))
        link.unlink()
        link.symlink_to(replacement)
        self.select(panel.case_table, 0)
        self.select(dialog.definition_table, 0)
        self.assertTrue(dialog.start_run(self.root / "automatic.csv"))
        self.wait_until(lambda: not dialog.is_running())
        for target in (original, replacement, link):
            contents = target.read_bytes()
            self.assertTrue(dialog._save_results(target))
            self.wait_until(lambda: not dialog.is_running())
            self.assertIn("Save failed", dialog.result_status.text())
            self.assertEqual(contents, target.read_bytes())

    def test_automatic_export_close_waits_for_writer_and_small_dialog_remains_usable(
        self,
    ):
        _window, panel, dialog = self.make_window()
        self.select(panel.case_table, 0)
        self.select(dialog.definition_table, 0)
        entered, release = threading.Event(), threading.Event()
        finished = []
        dialog.run_finished.connect(lambda: finished.append(True))
        original = sectional_dialog.write_sectional_csv

        def writer(*args):
            entered.set()
            release.wait(5)
            return original(*args)

        self.addCleanup(release.set)
        dialog.resize(640, 500)
        self.app.processEvents()
        for button in (
            dialog.btn_run,
            dialog.btn_cancel,
            dialog.btn_retry_save,
            dialog.btn_close,
        ):
            self.assertTrue(dialog.rect().contains(button.geometry()))
        with patch.object(sectional_dialog, "write_sectional_csv", side_effect=writer):
            self.assertTrue(dialog.start_run(self.root / "slow.csv"))
            self.wait_until(entered.is_set)
            self.assertEqual([], finished)
            self.assertTrue(panel._external_run_active)
            self.assertFalse(
                panel.start_run(panel.case_rows, 1, 0, self.root / "normal.csv")
            )
            dialog.close()
            self.assertTrue(dialog.isVisible())
            self.assertTrue(dialog.is_running())
            release.set()
            self.wait_until(lambda: not dialog.is_running())
        self.wait_until(lambda: not dialog.isVisible())
        self.assertEqual([True], finished)
        self.assertTrue((self.root / "slow.csv").exists())
