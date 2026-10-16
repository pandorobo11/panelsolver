from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets
from shiboken6 import delete, isValid

from panelsolver.app import (
    DEFAULT_CHECKPOINT_CASES,
    GuiRunRequest,
    GuiRunResult,
    OutputIssue,
    OutputKind,
    OutputPhase,
    SolverGuiAdapters,
)
from panelsolver.app.cases_panel import CasesPanel
from panelsolver.app.main_window import MainWindow
from panelsolver.core import (
    CaseSignature,
    CsvProjection,
    SchedulerCancelled,
    canonical_json,
)
from panelsolver.domains.fmf import gui_spec as fmf_solver_spec
from panelsolver.domains.hypersonic import gui_spec as newt_solver_spec
from tests.path_assertions import assert_paths_equivalent


def _signature(label: str) -> CaseSignature:
    envelope = {"fixture": label}
    payload = canonical_json(envelope)
    return CaseSignature(
        hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        payload,
        envelope,
    )


def _adapters(rows, run_cases):
    signatures = {str(row["case_id"]): _signature(str(row["case_id"])) for row in rows}
    return SolverGuiAdapters(
        read_cases=lambda _path: rows,
        build_case_signature=lambda row: signatures[str(row["case_id"])],
        run_cases=run_cases,
        validate_output_path=lambda out, _input, _rows: Path(out),
        resolve_velocity_hat_stl=lambda _row: (1.0, 0.0, 0.0),
    ), signatures


class _FakeViewer(QtWidgets.QWidget):
    log_message = QtCore.Signal(str)
    save_selected_images_requested = QtCore.Signal()

    def __init__(self) -> None:
        super().__init__()
        self.loaded = []
        self.cleared = 0
        self.rows = ()
        self.selected_rows = ()
        self.input_path = None
        self.saved_rows = []
        self.loaded_path = None

    def open_vtp(self) -> None:
        pass

    def load_vtp(self, *args) -> None:
        self.loaded.append(args)
        self.loaded_path = Path(args[0]).expanduser().resolve(strict=False)

    def invalidate_vtp_artifact(self, path: str) -> None:
        invalidated = Path(path).expanduser().resolve(strict=False)
        if self.loaded_path == invalidated:
            self.clear_view()

    def clear_view(self) -> None:
        self.cleared += 1
        self.loaded_path = None

    def set_artifact_view_state(self, state) -> None:
        self.artifact_state = state

    def set_case_rows(self, rows) -> None:
        self.rows = tuple(rows)

    def set_selected_case_rows(self, rows) -> None:
        self.selected_rows = tuple(rows)

    def set_input_path(self, path) -> None:
        self.input_path = path

    def save_images_for_case_rows(self, rows) -> None:
        self.saved_rows.append(list(rows))


class RunLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def own_widget(self, widget):
        # Keep every fixture alive (including earlier subTest iterations) until
        # unittest cleanup. Worker-triggered cyclic GC must never own Qt teardown.
        self.addCleanup(self.dispose_widget, widget)
        return widget

    def dispose_widget(self, widget) -> None:
        if not isValid(widget):
            return  # A registered parent has already deleted this child.
        self.assertEqual(QtCore.QThread.currentThread(), self.app.thread())
        panels = widget.findChildren(CasesPanel)
        if isinstance(widget, CasesPanel):
            panels.append(widget)
        for panel in panels:
            if panel.is_running():
                panel.cancel_run()
                self.wait_until(lambda active=panel: not active.is_running())
        widget.close()
        # close() only hides a widget; processEvents() need not deliver deferred
        # deletes outside exec(). Destroy now, with Python layout state intact.
        delete(widget)

    def wait_until(self, predicate, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        while not predicate():
            self.app.processEvents()
            if time.monotonic() >= deadline:
                self.fail("timed out waiting for Qt lifecycle")
            time.sleep(0.002)
        self.app.processEvents()

    def make_panel(
        self, runner, *, rows=None, artifact_reader=None, spec_factory=fmf_solver_spec
    ):
        rows = ({"case_id": "one"}, {"case_id": "two"}) if rows is None else tuple(rows)
        adapters, signatures = _adapters(rows, runner)
        panel = CasesPanel(
            spec_factory(adapters=adapters),
            artifact_reader=artifact_reader or (lambda _path: object()),
        )
        self.own_widget(panel)
        panel.case_rows = rows
        panel.input_path = Path("cases.csv")
        panel.btn_run.setEnabled(True)
        return panel, rows, signatures

    def test_typed_request_progress_logs_completion_view_and_cleanup(self) -> None:
        captured = {}
        with tempfile.TemporaryDirectory(prefix="phase6_run_") as directory:
            vtp_path = Path(directory) / "outputs" / "one.vtp"

            def runner(request):
                captured["request"] = request
                request.log("[SAVE] checkpoint 1/2 -> results.csv")
                request.progress(1, 2)
                request.log("[SAVE] final 2/2 -> results.csv")
                request.progress(2, 2)
                return GuiRunResult(vtp_path, request.rows[0])

            rows = ({"case_id": "one"}, {"case_id": "two"})
            adapters, signatures = _adapters(rows, runner)
            artifact = SimpleNamespace(
                field_data={
                    "case_id": ["one"],
                    "case_signature": [signatures["one"].digest],
                }
            )
            panel = CasesPanel(
                fmf_solver_spec(adapters=adapters),
                artifact_reader=lambda _path: artifact,
            )
            self.own_widget(panel)
            panel.case_rows = rows
            panel.input_path = Path(directory) / "cases.csv"
            loaded = []
            finished = []
            panel.vtp_loaded.connect(lambda *args: loaded.append(args))
            panel.run_finished.connect(lambda: finished.append(True))

            self.assertTrue(
                panel.start_run(rows, 2, 17, Path(directory) / "results.csv")
            )
            self.assertEqual("0/2", panel.progress.text())
            self.assertEqual("info", panel.progress.property("fluentStatus"))
            self.assertTrue(panel.progress.property("fluentBusy"))
            self.assertFalse(panel.btn_pick_input.isEnabled())
            self.assertTrue(panel.btn_cancel.isEnabled())
            self.assertTrue(panel.btn_diagnostics.isEnabled())
            self.assertFalse(panel.btn_diagnostics.isChecked())
            self.assertTrue(panel.log.isHidden())
            panel.btn_diagnostics.click()
            self.assertTrue(panel.btn_diagnostics.isChecked())
            self.assertFalse(panel.log.isHidden())
            self.wait_until(lambda: not panel.is_running())

            self.assertIsInstance(captured["request"], GuiRunRequest)
            self.assertEqual(2, captured["request"].workers)
            self.assertEqual(17, captured["request"].checkpoint_every_cases)
            assert_paths_equivalent(
                self, Path(directory) / "outputs", captured["request"].vtp_dir
            )
            self.assertEqual("Completed", panel.progress.text())
            self.assertEqual("success", panel.progress.property("fluentStatus"))
            self.assertFalse(panel.progress.property("fluentBusy"))
            self.assertIn("[SAVE] checkpoint 1/2", panel.log.toPlainText())
            self.assertIn("[SAVE] final 2/2", panel.log.toPlainText())
            self.assertEqual(1, len(loaded))
            self.assertEqual("one", loaded[0][2]["case_id"])
            self.assertEqual([True], finished)
            self.assertIsNone(panel._run_worker)
            self.assertTrue(panel.btn_pick_input.isEnabled())
            self.assertFalse(panel.btn_cancel.isEnabled())
            self.assertTrue(panel.btn_diagnostics.isChecked())
            self.assertFalse(panel.log.isHidden())

    def test_vtp_output_failures_complete_once_with_bounded_summary_and_recover_ui(
        self,
    ) -> None:
        issues = tuple(
            OutputIssue(
                OutputKind.VTP,
                OutputPhase.WRITE,
                f"outputs/case_{index}.vtp",
                f"save failure {index}",
                f"case_{index}",
            )
            for index in range(7)
        )
        rows = tuple({"case_id": f"case_{index}"} for index in range(7))

        def runner(request):
            request.progress(7, 7)
            return GuiRunResult(
                calculation_completed_cases=7,
                calculation_total_cases=7,
                summary_csv_saved=True,
                vtp_requested=7,
                vtp_saved=0,
                output_issues=issues,
            )

        panel, rows, _ = self.make_panel(runner, rows=rows)
        with patch.object(QtWidgets.QMessageBox, "warning") as warning:
            self.assertTrue(
                panel.start_run(rows, 1, DEFAULT_CHECKPOINT_CASES, "results.csv")
            )
            self.wait_until(lambda: not panel.is_running())

        self.assertEqual("Completed with output errors", panel.progress.text())
        self.assertEqual("warning", panel.progress.property("fluentStatus"))
        self.assertFalse(panel.progress.property("fluentBusy"))
        warning.assert_called_once()
        message = warning.call_args.args[2]
        self.assertIn("7/7 cases completed", message)
        self.assertIn("VTP: 0 saved, 7 failed", message)
        self.assertIn("case_0: save failure 0", message)
        self.assertIn("... and 2 more", message)
        self.assertNotIn("case_6: save failure 6", message)
        self.assertTrue(panel.btn_run.isEnabled())
        self.assertTrue(panel.btn_pick_input.isEnabled())
        self.assertFalse(panel.btn_cancel.isEnabled())

    def test_failed_vtp_is_invalidated_until_same_case_path_succeeds(self) -> None:
        with tempfile.TemporaryDirectory(prefix="stale_vtp_gui_") as directory:
            root = Path(directory)
            vtp_path = root / "outputs" / "one.vtp"
            vtp_path.parent.mkdir()
            vtp_path.write_text("previous run", encoding="utf-8")
            rows = ({"case_id": "one"},)
            calls = 0

            def runner(request):
                nonlocal calls
                calls += 1
                if calls == 1:
                    issue = OutputIssue(
                        OutputKind.VTP,
                        OutputPhase.WRITE,
                        str(vtp_path),
                        "permission denied",
                        "one",
                    )
                    return GuiRunResult(
                        calculation_completed_cases=1,
                        calculation_total_cases=1,
                        summary_csv_saved=True,
                        vtp_requested=1,
                        vtp_saved=0,
                        output_issues=(issue,),
                    )
                return GuiRunResult(
                    first_vtp_path=vtp_path,
                    first_case_row=request.rows[0],
                    calculation_completed_cases=1,
                    calculation_total_cases=1,
                    summary_csv_saved=True,
                    vtp_requested=1,
                    vtp_saved=1,
                )

            adapters, signatures = _adapters(rows, runner)
            artifact = SimpleNamespace(
                field_data={
                    "case_id": ["one"],
                    "case_signature": [signatures["one"].digest],
                }
            )
            panel = CasesPanel(
                fmf_solver_spec(adapters=adapters),
                artifact_reader=lambda _path: artifact,
            )
            self.own_widget(panel)
            panel.case_rows = rows
            panel.input_path = root / "cases.csv"
            panel._populate_case_table()
            viewer = _FakeViewer()
            window = MainWindow(panel.spec, cases_panel=panel, viewer_panel=viewer)
            self.own_widget(window)

            panel.case_table.selectRow(0)
            self.assertEqual(vtp_path.resolve(), viewer.loaded_path)
            initial_loads = len(viewer.loaded)

            with patch.object(QtWidgets.QMessageBox, "warning"):
                self.assertTrue(panel.start_run(rows, 1, 1, root / "results.csv"))
                self.wait_until(lambda: not panel.is_running())

            self.assertIsNone(viewer.loaded_path)
            panel.case_table.clearSelection()
            panel.case_table.selectRow(0)
            self.assertEqual(initial_loads, len(viewer.loaded))
            self.assertIsNone(viewer.loaded_path)

            self.assertTrue(panel.start_run(rows, 1, 1, root / "results.csv"))
            self.wait_until(lambda: not panel.is_running())
            self.assertEqual(vtp_path.resolve(), viewer.loaded_path)
            loads_after_success = len(viewer.loaded)
            panel.case_table.clearSelection()
            panel.case_table.selectRow(0)
            self.assertEqual(loads_after_success + 1, len(viewer.loaded))
            window.close()

    def test_summary_csv_failure_is_completed_output_failure(self) -> None:
        issue = OutputIssue(
            OutputKind.SUMMARY_CSV,
            OutputPhase.FINAL,
            "results.csv",
            "permission denied",
        )

        def runner(_request):
            return GuiRunResult(
                calculation_completed_cases=2,
                calculation_total_cases=2,
                summary_csv_saved=False,
                output_issues=(issue,),
            )

        panel, rows, _ = self.make_panel(runner)
        with patch.object(QtWidgets.QMessageBox, "warning") as warning:
            self.assertTrue(
                panel.start_run(rows, 1, DEFAULT_CHECKPOINT_CASES, "results.csv")
            )
            self.wait_until(lambda: not panel.is_running())

        self.assertEqual("Completed with output errors", panel.progress.text())
        self.assertIn("Summary CSV: failed", warning.call_args.args[2])
        self.assertNotIn("[OK] Wrote results", panel.log.toPlainText())

    @staticmethod
    def unsaved_result():
        return GuiRunResult(
            calculation_completed_cases=2,
            calculation_total_cases=2,
            summary_csv_saved=False,
            output_issues=(
                OutputIssue(
                    OutputKind.SUMMARY_CSV,
                    OutputPhase.FINAL,
                    "results.csv",
                    "disk full",
                ),
            ),
            unsaved_summary_csv=CsvProjection(
                ("case_id", "CA"),
                ({"case_id": "one", "CA": 0.25}, {"case_id": "two", "CA": 0.5}),
            ),
        )

    def test_retry_summary_after_reload_saves_original_snapshot_without_solving(self):
        for factory in (fmf_solver_spec, newt_solver_spec):
            with (
                self.subTest(domain=factory.__module__),
                tempfile.TemporaryDirectory() as directory,
            ):
                calls = []

                def runner(request, captured=calls):
                    captured.append(request)
                    return self.unsaved_result()

                panel, rows, _ = self.make_panel(runner, spec_factory=factory)
                with patch.object(QtWidgets.QMessageBox, "warning"):
                    panel.start_run(rows, 1, 0, Path(directory) / "result.csv")
                    self.wait_until(lambda active=panel: not active.is_running())
                retained = panel._summary_retry
                self.assertFalse(panel.btn_retry_save.isHidden())
                self.assertTrue(panel.btn_retry_save.isEnabled())
                panel.clear_loaded_cases()
                panel.input_path = Path(directory) / "new.csv"
                panel.case_rows = ({"case_id": "new", "stl_path": "new.stl"},)
                self.assertIs(retained, panel._summary_retry)
                self.assertIn("cases.csv", panel.lbl_summary_save.text())
                output = Path(directory) / "recovered.csv"
                output.write_text("previous valid file")
                with patch.object(
                    QtWidgets.QFileDialog,
                    "getSaveFileName",
                    return_value=(str(output), ""),
                ):
                    with patch(
                        "panelsolver.app.csv_writer.os.replace",
                        side_effect=OSError("disk full"),
                    ):
                        self.assertTrue(panel.retry_summary_save())
                        self.wait_until(lambda active=panel: not active.is_running())
                    self.assertEqual(output.read_text(), "previous valid file")
                    self.assertIs(retained, panel._summary_retry)
                    self.assertTrue(panel.retry_summary_save())
                    self.wait_until(lambda active=panel: not active.is_running())
                self.assertEqual(len(calls), 1)
                self.assertIn("one,0.25", output.read_text(encoding="utf-8-sig"))
                self.assertNotIn("new", output.read_text())
                self.assertIsNone(panel._summary_retry)
                self.assertTrue(panel.btn_retry_save.isHidden())
                self.assertEqual(panel.progress.text(), "Summary CSV saved")

    def test_retry_summary_protects_old_and_current_unselected_inputs_and_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = (
                {"case_id": "one", "stl_path": "one.stl"},
                {"case_id": "two", "stl_path": "two.stl"},
            )
            panel, rows, _ = self.make_panel(lambda _: self.unsaved_result(), rows=rows)
            panel.input_path = root / "old.csv"
            panel.sectional_definition_paths = (root / "sections.csv",)
            with patch.object(QtWidgets.QMessageBox, "warning"):
                panel.start_run(rows[:1], 1, 0, root / "result.csv")
                self.wait_until(lambda: not panel.is_running())
            panel.input_path = root / "new.csv"
            panel.case_rows = ({"case_id": "new", "stl_path": "new.stl"},)
            paths = [
                root / name
                for name in (
                    "old.csv",
                    "one.stl",
                    "two.stl",
                    "sections.csv",
                    "new.csv",
                    "new.stl",
                    "outputs/two.vtp",
                    "outputs/new.vtp",
                )
            ]
            for path in paths:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("protected")
            alias = root / "alias.csv"
            os.link(root / "two.stl", alias)
            symlink = root / "link.csv"
            symlink.symlink_to(root / "one.stl")
            for path in (*paths, alias, symlink):
                with (
                    self.subTest(path=path.name),
                    patch.object(
                        QtWidgets.QFileDialog,
                        "getSaveFileName",
                        return_value=(str(path), ""),
                    ),
                ):
                    self.assertFalse(panel.retry_summary_save())
                    self.assertEqual(path.read_text(), "protected")
                    self.assertTrue(panel.btn_retry_save.isEnabled())

    def test_retry_summary_cancel_and_new_failed_run_keep_snapshot_success_replaces_it(
        self,
    ):
        outcomes = [
            self.unsaved_result(),
            RuntimeError("new solve failed"),
            SchedulerCancelled("cancelled"),
            GuiRunResult(summary_csv_saved=True),
        ]

        def runner(_):
            result = outcomes.pop(0)
            if isinstance(result, Exception):
                raise result
            return result

        panel, rows, _ = self.make_panel(runner)
        with patch.object(QtWidgets.QMessageBox, "warning"):
            panel.start_run(rows, 1, 0, "result.csv")
            self.wait_until(lambda: not panel.is_running())
        retained = panel._summary_retry
        with patch.object(
            QtWidgets.QFileDialog, "getSaveFileName", return_value=("", "")
        ):
            self.assertFalse(panel.retry_summary_save())
        panel.set_external_run_active(True)
        self.assertFalse(panel.btn_retry_save.isEnabled())
        self.assertFalse(panel.retry_summary_save())
        panel.set_external_run_active(False)
        for _ in range(2):
            panel.start_run(rows, 1, 0, "new.csv")
            self.assertFalse(panel.btn_retry_save.isEnabled())
            self.wait_until(lambda: not panel.is_running())
            self.assertIs(retained, panel._summary_retry)
        panel.start_run(rows, 1, 0, "new.csv")
        self.wait_until(lambda: not panel.is_running())
        self.assertIsNone(panel._summary_retry)

    def test_summary_failure_during_pending_close_preserves_results_even_after_cancel(
        self,
    ):
        entered, release = threading.Event(), threading.Event()

        def runner(_):
            entered.set()
            release.wait(3)
            return self.unsaved_result()

        panel, rows, _ = self.make_panel(runner)
        window = MainWindow(panel.spec, cases_panel=panel, viewer_panel=_FakeViewer())
        self.own_widget(window)
        window.show()
        with patch.object(QtWidgets.QMessageBox, "warning"):
            panel.start_run(rows, 1, 0, "result.csv")
            self.wait_until(entered.is_set)
            window.close()
            self.assertTrue(window._close_when_run_finishes)
            release.set()
            self.wait_until(lambda: not panel.is_running())
        self.assertTrue(window.isVisible())
        self.assertFalse(window._close_when_run_finishes)
        self.assertTrue(panel.btn_retry_save.isEnabled())
        self.discard_and_close(window)

    def test_summary_retry_worker_blocks_runs_and_keeps_window_open_on_failure(self):
        from panelsolver.app import run_lifecycle

        panel, rows, _ = self.make_panel(lambda _: self.unsaved_result())
        window = MainWindow(panel.spec, cases_panel=panel, viewer_panel=_FakeViewer())
        self.own_widget(window)
        window.show()
        with patch.object(QtWidgets.QMessageBox, "warning"):
            panel.start_run(rows, 1, 0, "result.csv")
            self.wait_until(lambda: not panel.is_running())
        entered, release = threading.Event(), threading.Event()

        def fail(*_):
            entered.set()
            release.wait(3)
            raise OSError("disk full")

        with (
            patch.object(run_lifecycle, "write_summary_snapshot", side_effect=fail),
            patch.object(
                QtWidgets.QFileDialog, "getSaveFileName", return_value=("retry.csv", "")
            ),
        ):
            panel.retry_summary_save()
            self.wait_until(entered.is_set)
            self.assertFalse(panel.btn_cancel.isEnabled())
            self.assertFalse(panel.btn_run.isEnabled())
            self.assertFalse(panel.btn_reload_input.isEnabled())
            self.assertFalse(panel.start_run(rows, 1, 0, "other.csv"))
            window.close()
            self.assertTrue(window._close_when_run_finishes)
            release.set()
            self.wait_until(lambda: not panel.is_running())
        self.assertTrue(window.isVisible())
        self.assertFalse(window._close_when_run_finishes)
        self.assertTrue(panel.btn_retry_save.isEnabled())
        self.discard_and_close(window)

    def watch_worker_destruction(self, worker) -> list[int]:
        # Record only the destroying thread; never retain the worker itself.
        destroyed: list[int] = []
        worker.destroyed.connect(
            lambda: destroyed.append(threading.get_ident()),
            QtCore.Qt.ConnectionType.DirectConnection,
        )
        return destroyed

    def test_run_and_summary_export_workers_are_destroyed_on_gui_thread(self):
        # A worker destroyed on its own QThread can deadlock: ~QObject holds
        # Qt's connection lock while a PySide override waits for the GIL that
        # the GUI thread holds while it waits for that lock.
        from panelsolver.app import run_lifecycle

        def cancel(_request):
            raise SchedulerCancelled("stop")

        def fail(_request):
            raise RuntimeError("solver failed")

        gui_thread = threading.get_ident()
        for name, runner in (
            ("completed", lambda _request: self.unsaved_result()),
            ("failed", fail),
            ("canceled", cancel),
        ):
            with self.subTest(outcome=name):
                panel, rows, _ = self.make_panel(runner)
                with patch.object(QtWidgets.QMessageBox, "warning"):
                    self.assertTrue(panel.start_run(rows, 1, 0, "result.csv"))
                    destroyed = self.watch_worker_destruction(panel._run_worker)
                    self.wait_until(
                        lambda panel=panel, destroyed=destroyed: (
                            not panel.is_running() and destroyed
                        )
                    )
                self.assertEqual([gui_thread], destroyed)

        panel, rows, _ = self.make_panel(lambda _request: self.unsaved_result())
        with patch.object(QtWidgets.QMessageBox, "warning"):
            panel.start_run(rows, 1, 0, "result.csv")
            self.wait_until(lambda: not panel.is_running())
        for name, effect in (("failed", OSError("disk full")), ("saved", None)):
            with self.subTest(export=name):
                with (
                    patch.object(
                        run_lifecycle,
                        "write_summary_snapshot",
                        side_effect=effect,
                        return_value=Path("retry.csv"),
                    ),
                    patch.object(
                        QtWidgets.QFileDialog,
                        "getSaveFileName",
                        return_value=("retry.csv", ""),
                    ),
                ):
                    self.assertTrue(panel.retry_summary_save())
                    destroyed = self.watch_worker_destruction(panel._run_worker)
                    self.wait_until(
                        lambda panel=panel, destroyed=destroyed: (
                            not panel.is_running() and destroyed
                        )
                    )
                self.assertEqual([gui_thread], destroyed)

    def discard_and_close(self, window) -> None:
        with patch.object(
            QtWidgets.QMessageBox,
            "warning",
            return_value=QtWidgets.QMessageBox.StandardButton.Discard,
        ):
            window.close()
        self.assertFalse(window.isVisible())

    def test_output_errors_dialog_offers_retry_that_saves_after_cleanup(self):
        panel, rows, _ = self.make_panel(lambda _: self.unsaved_result())
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "recovered.csv"
            with (
                patch.object(
                    QtWidgets.QMessageBox,
                    "warning",
                    return_value=QtWidgets.QMessageBox.StandardButton.Retry,
                ) as warning,
                patch.object(
                    QtWidgets.QFileDialog,
                    "getSaveFileName",
                    return_value=(str(output), ""),
                ) as chooser,
            ):
                panel.start_run(rows, 1, 0, Path(directory) / "result.csv")
                self.wait_until(lambda: output.exists() and not panel.is_running())
            message = warning.call_args.args[2]
            self.assertIn("Summary CSV: failed", message)
            self.assertIn("Results are retained", message)
            self.assertIn("Retry Save...", message)
            chooser.assert_called_once()
            self.assertIn("one,0.25", output.read_text(encoding="utf-8-sig"))
        self.assertIsNone(panel._summary_retry)
        self.assertTrue(panel.btn_retry_save.isHidden())

    def test_output_errors_dialog_close_keeps_retained_summary(self):
        panel, rows, _ = self.make_panel(lambda _: self.unsaved_result())
        with (
            patch.object(
                QtWidgets.QMessageBox,
                "warning",
                return_value=QtWidgets.QMessageBox.StandardButton.Close,
            ),
            patch.object(QtWidgets.QFileDialog, "getSaveFileName") as chooser,
        ):
            panel.start_run(rows, 1, 0, "result.csv")
            self.wait_until(lambda: not panel.is_running())
            self.app.processEvents()
        chooser.assert_not_called()
        self.assertIsNotNone(panel._summary_retry)
        self.assertTrue(panel.btn_retry_save.isEnabled())

    def test_close_with_unsaved_summary_asks_before_discarding(self):
        buttons = QtWidgets.QMessageBox.StandardButton
        panel, rows, _ = self.make_panel(lambda _: self.unsaved_result())
        window = MainWindow(panel.spec, cases_panel=panel, viewer_panel=_FakeViewer())
        self.own_widget(window)
        window.show()
        with patch.object(QtWidgets.QMessageBox, "warning"):
            panel.start_run(rows, 1, 0, "result.csv")
            self.wait_until(lambda: not panel.is_running())
        with patch.object(
            QtWidgets.QMessageBox, "warning", return_value=buttons.Cancel
        ) as warning:
            window.close()
        self.assertTrue(window.isVisible())
        self.assertIn("2 case(s) from cases.csv", warning.call_args.args[2])
        with (
            patch.object(QtWidgets.QMessageBox, "warning", return_value=buttons.Save),
            patch.object(
                QtWidgets.QFileDialog, "getSaveFileName", return_value=("", "")
            ),
        ):
            window.close()
        self.assertTrue(window.isVisible())
        self.assertFalse(window._close_when_run_finishes)
        self.assertIsNotNone(panel._summary_retry)
        self.discard_and_close(window)

    def test_close_save_choice_closes_window_after_successful_retry(self):
        panel, rows, _ = self.make_panel(lambda _: self.unsaved_result())
        window = MainWindow(panel.spec, cases_panel=panel, viewer_panel=_FakeViewer())
        self.own_widget(window)
        window.show()
        with patch.object(QtWidgets.QMessageBox, "warning"):
            panel.start_run(rows, 1, 0, "result.csv")
            self.wait_until(lambda: not panel.is_running())
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(
                QtWidgets.QMessageBox,
                "warning",
                return_value=QtWidgets.QMessageBox.StandardButton.Save,
            ),
            patch.object(
                QtWidgets.QFileDialog,
                "getSaveFileName",
                return_value=(str(Path(directory) / "recovered.csv"), ""),
            ),
        ):
            window.close()
            self.assertTrue(window._close_when_run_finishes)
            self.wait_until(lambda: not window.isVisible())
            self.assertTrue((Path(directory) / "recovered.csv").exists())
        self.assertIsNone(panel._summary_retry)

    def test_complete_checkpoint_summary_is_not_displayed_as_failed(self) -> None:
        def runner(_request):
            return GuiRunResult(
                calculation_completed_cases=2,
                calculation_total_cases=2,
                summary_csv_saved=True,
            )

        panel, rows, _ = self.make_panel(runner)
        with patch.object(QtWidgets.QMessageBox, "warning") as warning:
            self.assertTrue(panel.start_run(rows, 1, 2, "results.csv"))
            self.wait_until(lambda: not panel.is_running())

        self.assertEqual("Completed", panel.progress.text())
        self.assertIn("[OK] Wrote results: results.csv", panel.log.toPlainText())
        warning.assert_not_called()

    def test_cancellation_before_and_after_progress(self) -> None:
        for emit_progress in (False, True):
            with self.subTest(emit_progress=emit_progress):
                entered = threading.Event()

                def runner(
                    request,
                    *,
                    should_emit=emit_progress,
                    started=entered,
                ):
                    if should_emit:
                        request.progress(1, 2)
                    started.set()
                    while not request.cancel_requested():
                        time.sleep(0.001)
                    raise SchedulerCancelled("case boundary")

                panel, rows, _ = self.make_panel(runner)
                self.assertTrue(
                    panel.start_run(rows, 1, DEFAULT_CHECKPOINT_CASES, "results.csv")
                )
                self.wait_until(entered.is_set)
                self.assertFalse(panel.btn_reload_input.isEnabled())
                with patch(
                    "panelsolver.app.cases_panel.absolute_input_path"
                ) as source_path:
                    panel.reload_input_file()
                source_path.assert_not_called()
                if emit_progress:
                    self.wait_until(
                        lambda active_panel=panel: active_panel.progress.text() == "1/2"
                    )
                panel.cancel_run()
                self.assertIn("Cancelling", panel.progress.text())
                self.assertEqual("warning", panel.progress.property("fluentStatus"))
                self.assertTrue(panel.progress.property("fluentBusy"))
                self.assertFalse(panel.btn_cancel.isEnabled())
                self.wait_until(
                    lambda active_panel=panel: not active_panel.is_running()
                )
                self.assertEqual("Canceled", panel.progress.text())
                self.assertEqual("warning", panel.progress.property("fluentStatus"))
                self.assertFalse(panel.progress.property("fluentBusy"))
                self.assertIn("[CANCEL] Run canceled.", panel.log.toPlainText())
                self.assertTrue(panel.btn_reload_input.isEnabled())
                if emit_progress:
                    self.assertGreaterEqual(panel.progress.value(), 1)

    def test_primary_failure_is_not_hidden_by_cancel_and_double_run_is_rejected(
        self,
    ) -> None:
        entered = threading.Event()
        calls = []

        def runner(request):
            calls.append(request)
            entered.set()
            while not request.cancel_requested():
                time.sleep(0.001)
            raise RuntimeError("primary solver failure")

        panel, rows, _ = self.make_panel(runner)
        self.assertTrue(
            panel.start_run(rows, 1, DEFAULT_CHECKPOINT_CASES, "results.csv")
        )
        self.wait_until(entered.is_set)
        self.assertFalse(
            panel.start_run(rows, 1, DEFAULT_CHECKPOINT_CASES, "second.csv")
        )
        panel.cancel_run()
        self.wait_until(lambda: not panel.is_running())
        self.assertEqual(1, len(calls))
        self.assertEqual("Failed", panel.progress.text())
        self.assertEqual("danger", panel.progress.property("fluentStatus"))
        self.assertFalse(panel.progress.property("fluentBusy"))
        self.assertIn("primary solver failure", panel.log.toPlainText())
        self.assertNotIn("Run canceled.", panel.log.toPlainText())
        self.assertFalse(panel.btn_diagnostics.isChecked())
        self.assertTrue(panel.log.isHidden())

    def test_status_resets_for_next_run_and_clear_loaded_cases(self) -> None:
        entered = (threading.Event(), threading.Event())
        release = (threading.Event(), threading.Event())
        calls = 0

        def runner(_request):
            nonlocal calls
            index = calls
            calls += 1
            entered[index].set()
            release[index].wait(timeout=3.0)
            return GuiRunResult()

        panel, rows, _ = self.make_panel(runner)
        self.assertEqual("Idle", panel.progress.text())
        self.assertEqual("neutral", panel.progress.property("fluentStatus"))
        self.assertFalse(panel.progress.property("fluentBusy"))

        for index in range(2):
            self.assertTrue(
                panel.start_run(
                    rows,
                    1,
                    DEFAULT_CHECKPOINT_CASES,
                    f"results_{index}.csv",
                )
            )
            self.assertEqual("0/2", panel.progress.text())
            self.assertEqual("info", panel.progress.property("fluentStatus"))
            self.assertTrue(panel.progress.property("fluentBusy"))
            self.wait_until(entered[index].is_set)
            release[index].set()
            self.wait_until(lambda: not panel.is_running())
            self.assertEqual("Completed", panel.progress.text())
            self.assertEqual("success", panel.progress.property("fluentStatus"))
            self.assertFalse(panel.progress.property("fluentBusy"))

        panel.clear_loaded_cases()
        self.assertEqual("Idle", panel.progress.text())
        self.assertEqual(
            (0, 1, 0),
            (
                panel.progress.minimum(),
                panel.progress.maximum(),
                panel.progress.value(),
            ),
        )
        self.assertEqual("neutral", panel.progress.property("fluentStatus"))
        self.assertFalse(panel.progress.property("fluentBusy"))

    def test_run_scope_wording_stays_disabled_during_run_and_restores(self) -> None:
        for selected_row, expected_label in (
            (None, "Run All Cases"),
            (1, "Run Selected Cases"),
        ):
            with self.subTest(selected_row=selected_row):
                entered = threading.Event()
                release = threading.Event()

                def runner(_request, *, started=entered, finish=release):
                    started.set()
                    finish.wait(timeout=3.0)
                    return GuiRunResult()

                panel, rows, _ = self.make_panel(runner)
                panel._populate_case_table()
                if selected_row is not None:
                    panel.case_table.selectRow(selected_row)
                run_rows = panel.selected_or_all_case_rows()
                expected_rows = list(rows if selected_row is None else rows[1:2])
                self.assertEqual(expected_rows, run_rows)
                self.assertEqual(expected_label, panel.btn_run.text())

                self.assertTrue(panel.start_run(run_rows, 1, 1, "results.csv"))
                self.assertEqual(expected_label, panel.btn_run.text())
                self.assertFalse(panel.btn_run.isEnabled())
                self.wait_until(entered.is_set)
                release.set()
                self.wait_until(
                    lambda active_panel=panel: not active_panel.is_running()
                )

                self.assertEqual(expected_label, panel.btn_run.text())
                self.assertTrue(panel.btn_run.isEnabled())

    def test_both_products_defer_active_close_until_thread_cleanup(self) -> None:
        for spec_factory in (fmf_solver_spec, newt_solver_spec):
            with self.subTest(product=spec_factory.__module__):
                entered = threading.Event()
                release = threading.Event()

                def runner(request, *, started=entered, finish=release):
                    started.set()
                    while not request.cancel_requested():
                        time.sleep(0.001)
                    finish.wait(timeout=3.0)
                    raise SchedulerCancelled("case boundary")

                panel, rows, _ = self.make_panel(
                    runner,
                    spec_factory=spec_factory,
                )
                viewer = _FakeViewer()
                window = MainWindow(
                    panel.spec,
                    cases_panel=panel,
                    viewer_panel=viewer,
                )
                self.own_widget(window)
                window.show()
                self.assertEqual((1480, 900), (window.width(), window.height()))
                self.assertTrue(
                    panel.start_run(rows, 1, DEFAULT_CHECKPOINT_CASES, "results.csv")
                )
                self.wait_until(entered.is_set)

                first_event = QtGui.QCloseEvent()
                second_event = QtGui.QCloseEvent()
                with patch.object(
                    panel,
                    "cancel_run",
                    wraps=panel.cancel_run,
                ) as cancel:
                    window.closeEvent(first_event)
                    window.closeEvent(second_event)
                    cancel.assert_called_once_with()

                self.assertFalse(first_event.isAccepted())
                self.assertFalse(second_event.isAccepted())
                self.assertTrue(window._close_when_run_finishes)
                self.assertTrue(window.isVisible())
                self.assertEqual(
                    1,
                    panel.log.toPlainText().count("[CLOSE] Waiting"),
                )

                release.set()
                self.wait_until(lambda active=panel: not active.is_running())
                self.wait_until(
                    lambda active=window: not active._close_when_run_finishes
                )
                self.wait_until(lambda active=window: not active.isVisible())

        restarted_panel, _rows, _ = self.make_panel(
            lambda _request: GuiRunResult(),
            spec_factory=newt_solver_spec,
        )
        restarted = MainWindow(
            restarted_panel.spec,
            cases_panel=restarted_panel,
            viewer_panel=_FakeViewer(),
        )
        self.own_widget(restarted)
        restarted.show()
        self.assertTrue(restarted.isVisible())
        restarted.close()

    def test_failure_during_pending_close_still_waits_and_closes(self) -> None:
        entered = threading.Event()

        def runner(request):
            entered.set()
            while not request.cancel_requested():
                time.sleep(0.001)
            raise RuntimeError("solver failed during pending close")

        panel, rows, _ = self.make_panel(runner, spec_factory=newt_solver_spec)
        window = MainWindow(
            panel.spec,
            cases_panel=panel,
            viewer_panel=_FakeViewer(),
        )
        self.own_widget(window)
        window.show()
        self.assertTrue(
            panel.start_run(rows, 1, DEFAULT_CHECKPOINT_CASES, "results.csv")
        )
        self.wait_until(entered.is_set)

        event = QtGui.QCloseEvent()
        window.closeEvent(event)
        self.assertFalse(event.isAccepted())
        self.assertTrue(window.isVisible())
        self.wait_until(lambda: not panel.is_running())
        self.wait_until(lambda: not window.isVisible())
        self.assertIn("solver failed during pending close", panel.log.toPlainText())

    def test_normal_close_is_not_deferred(self) -> None:
        panel, _rows, _ = self.make_panel(lambda _request: GuiRunResult())
        window = MainWindow(
            panel.spec,
            cases_panel=panel,
            viewer_panel=_FakeViewer(),
        )
        self.own_widget(window)
        window.show()
        normal_event = QtGui.QCloseEvent()
        window.closeEvent(normal_event)
        self.assertTrue(normal_event.isAccepted())
        window.close()

    def test_main_window_routes_selected_rows_to_batch_export(self) -> None:
        panel, rows, _ = self.make_panel(lambda _request: GuiRunResult())
        panel._populate_case_table()
        panel.case_table.selectRow(1)
        viewer = _FakeViewer()
        window = MainWindow(panel.spec, cases_panel=panel, viewer_panel=viewer)
        self.own_widget(window)
        viewer.save_selected_images_requested.emit()
        self.assertEqual([[rows[1]]], viewer.saved_rows)
        window.close()


if __name__ == "__main__":
    unittest.main()
