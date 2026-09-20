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

    def test_read_only_open_reload_invalid_reload_and_explicit_selection(self):
        window, panel, dialog = self.make_window()
        self.assertFalse(dialog.btn_run.isEnabled())
        self.assertFalse(dialog.start_run())
        self.assertEqual(2, dialog.definition_model.rowCount())
        index = dialog.definition_model.index(0, 0)
        self.assertFalse(
            dialog.definition_model.flags(index) & QtCore.Qt.ItemFlag.ItemIsEditable
        )
        self.assertFalse(dialog.definition_model.setData(index, "changed"))
        self.assertEqual("span", dialog.definitions[0].section_id)
        self.select(panel.case_table, 1)
        self.assertFalse(dialog.start_run())
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
        self.assertFalse(dialog.btn_run.isEnabled())
        self.select(dialog.definition_table, 0)
        self.definition_path.write_text(HEADER + "broken,0,0,0,0,0,0,4\n")
        dialog.reload_definitions()
        self.assertEqual((), dialog.definitions)
        self.assertIn("read failed", dialog.definition_status.text())
        self.assertFalse(dialog.start_run())
        self.assertFalse(dialog.btn_run.isEnabled())
        self.assertEqual(str(self.definition_path), dialog.path_value.text())
        window.open_sectional_loads()
        self.assertIs(window.sectional_dialog, dialog)

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
                    self.assertTrue(dialog.start_run())
                    self.wait_until(lambda dialog=dialog: not dialog.is_running())
                self.assertEqual(2, execute.call_count)
                self.assertTrue(
                    all(thread != gui_thread for thread in observed_threads)
                )
                self.assertEqual(expected, dialog.batch_result)
                self.assertIs(
                    dialog.batch_result.csv.rows[0], dialog.result_model.rows[0]
                )
                self.assertEqual("Completed", dialog.progress.text())
                self.assertTrue(dialog.btn_export.isEnabled())
                self.assertFalse((self.root / "unused").exists())
                output = self.root / f"{domain.RUNTIME_POLICY.product_id}.csv"
                self.assertTrue(dialog.export_results(output))
                self.wait_until(lambda dialog=dialog: not dialog.is_running())
                with output.open(encoding="utf-8-sig", newline="") as handle:
                    rows = list(csv.DictReader(handle))
                self.assertEqual(20, len(rows))
                self.assertEqual({"case_0", "case_1"}, {row["case_id"] for row in rows})

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
        self.assertTrue(dialog.start_run())
        self.wait_until(entered.is_set)
        self.assertFalse(dialog.start_run())
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
        self.assertTrue(dialog.export_results(output))
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
        self.assertTrue(dialog.start_run())
        self.wait_until(lambda: not dialog.is_running())
        self.assertTrue(
            panel.start_run(panel.case_rows, 1, 0, self.root / "normal.csv")
        )
        self.assertFalse(dialog.btn_run.isEnabled())
        self.assertFalse(dialog.btn_export.isEnabled())
        self.assertFalse(dialog.start_run())
        self.assertFalse(dialog.export_results(self.root / "normal.csv"))
        self.wait_until(entered.is_set)
        release.set()
        self.wait_until(lambda: not panel.is_running())
        self.assertTrue(dialog.btn_run.isEnabled())

    def test_cancellation_keeps_partial_result_and_export_failure_is_retryable(self):
        entered = threading.Event()

        def runner(request):
            entered.set()
            while not request.cancel_requested():
                time.sleep(0.002)
            first = sectional_batch.run_sectional_cases(
                request.rows[:1], fmf.RUNTIME_POLICY, request.definitions[:1]
            )
            rows = tuple(
                dict(
                    row, batch_status="cancelled", requested_pairs=4, completed_pairs=1
                )
                for row in first.csv.rows
            )
            return SectionalBatchResult(
                type(first.csv)(first.csv.columns, rows), "cancelled", 1, 4, 0, 2
            )

        _window, panel, dialog = self.make_window(runner=runner)
        self.select(panel.case_table, 0, 1)
        self.select(dialog.definition_table, 0, 1)
        self.assertTrue(dialog.start_run())
        self.wait_until(entered.is_set)
        dialog.cancel_run()
        self.assertIn("Cancelling", dialog.progress.text())
        self.wait_until(lambda: not dialog.is_running())
        self.assertEqual("cancelled", dialog.batch_result.status)
        self.assertIn("Cancelled: 1/4", dialog.result_status.text())
        retained = dialog.batch_result
        output = self.root / "result.csv"
        output.write_text("old valid contents")
        with patch(
            "panelsolver.app.csv_writer.os.replace", side_effect=OSError("disk failure")
        ):
            self.assertTrue(dialog.export_results(output))
            self.wait_until(lambda: not dialog.is_running())
        self.assertIs(retained, dialog.batch_result)
        self.assertIn("Export failed", dialog.result_status.text())
        self.assertEqual("old valid contents", output.read_text())
        with patch.object(
            sectional_batch, "execute_case", side_effect=AssertionError("recalculation")
        ):
            self.assertTrue(dialog.export_results(output))
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
                self.assertTrue(dialog.start_run())
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
        self.assertTrue(dialog.start_run())
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
            self.assertTrue(dialog.export_results(path))
            self.wait_until(lambda: not dialog.is_running())
            self.assertIn("Export failed", dialog.result_status.text())
            self.assertEqual(original, path.read_bytes())
            self.assertIs(retained, dialog.batch_result)
        self.assertTrue(dialog.export_results(self.root / "old-snapshot.csv"))
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
        self.assertTrue(dialog.start_run())
        self.wait_until(lambda: not dialog.is_running())
        for path in (self.definition_path, replacement, panel.input_path):
            original = path.read_bytes()
            self.assertTrue(dialog.export_results(path))
            self.wait_until(lambda: not dialog.is_running())
            self.assertIn("Export failed", dialog.result_status.text())
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
        self.assertTrue(dialog.start_run())
        self.wait_until(lambda: not dialog.is_running())
        for target in (original, replacement, link):
            contents = target.read_bytes()
            self.assertTrue(dialog.export_results(target))
            self.wait_until(lambda: not dialog.is_running())
            self.assertIn("Export failed", dialog.result_status.text())
            self.assertEqual(contents, target.read_bytes())

    def test_export_close_waits_for_writer_and_small_dialog_remains_usable(self):
        _window, panel, dialog = self.make_window()
        self.select(panel.case_table, 0)
        self.select(dialog.definition_table, 0)
        self.assertTrue(dialog.start_run())
        self.wait_until(lambda: not dialog.is_running())
        entered, release = threading.Event(), threading.Event()
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
            dialog.btn_export,
            dialog.btn_close,
        ):
            self.assertTrue(dialog.rect().contains(button.geometry()))
        with patch.object(sectional_dialog, "write_sectional_csv", side_effect=writer):
            self.assertTrue(dialog.export_results(self.root / "slow.csv"))
            self.wait_until(entered.is_set)
            dialog.close()
            self.assertTrue(dialog.isVisible())
            self.assertTrue(dialog.is_running())
            release.set()
            self.wait_until(lambda: not dialog.is_running())
        self.wait_until(lambda: not dialog.isVisible())
        self.assertTrue((self.root / "slow.csv").exists())
