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

from fmfsolver._frontend import _legacy_gui_spec as fmf_solver_spec
from newtsolver._frontend import _legacy_gui_spec as newt_solver_spec
from panelsolver.app import (
    DEFAULT_CHECKPOINT_CASES,
    ArtifactSignatureCandidates,
    GuiRunRequest,
    GuiRunResult,
    OutputIssue,
    OutputKind,
    OutputPhase,
    SolverGuiAdapters,
)
from panelsolver.app.cases_panel import CasesPanel
from panelsolver.app.main_window import MainWindow
from panelsolver.core import CaseSignature, SchedulerCancelled, canonical_json


def _signature(label: str) -> CaseSignature:
    envelope = {"fixture": label}
    payload = canonical_json(envelope)
    return CaseSignature(
        hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        payload,
        envelope,
    )


def _adapters(rows, run_cases):
    signatures = {
        str(row["case_id"]): ArtifactSignatureCandidates(
            _signature(str(row["case_id"]))
        )
        for row in rows
    }
    return SolverGuiAdapters(
        read_cases=lambda _path: rows,
        build_case_signatures=lambda row: signatures[str(row["case_id"])],
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
        rows = (
            (
                {"case_id": "one", "out_dir": "outputs"},
                {"case_id": "two", "out_dir": "outputs"},
            )
            if rows is None
            else tuple(rows)
        )
        adapters, signatures = _adapters(rows, runner)
        panel = CasesPanel(
            spec_factory(adapters=adapters),
            artifact_reader=artifact_reader or (lambda _path: object()),
        )
        panel.case_rows = rows
        panel.input_path = Path("cases.csv")
        panel.btn_run.setEnabled(True)
        return panel, rows, signatures

    def test_typed_request_progress_logs_completion_view_and_cleanup(self) -> None:
        captured = {}
        with tempfile.TemporaryDirectory(prefix="phase6_run_") as directory:
            vtp_path = Path(directory) / "one.vtp"

            def runner(request):
                captured["request"] = request
                request.log("[SAVE] checkpoint 1/2 -> results.csv")
                request.progress(1, 2)
                request.log("[SAVE] final 2/2 -> results.csv")
                request.progress(2, 2)
                return GuiRunResult(vtp_path, request.rows[0])

            rows = (
                {"case_id": "one", "out_dir": directory},
                {"case_id": "two", "out_dir": directory},
            )
            adapters, signatures = _adapters(rows, runner)
            artifact = SimpleNamespace(
                field_data={
                    "case_id": ["one"],
                    "case_signature": [signatures["one"].primary.digest],
                }
            )
            panel = CasesPanel(
                fmf_solver_spec(adapters=adapters),
                artifact_reader=lambda _path: artifact,
            )
            panel.case_rows = rows
            loaded = []
            finished = []
            panel.vtp_loaded.connect(lambda *args: loaded.append(args))
            panel.run_finished.connect(lambda: finished.append(True))

            self.assertTrue(
                panel.start_run(rows, 2, 17, Path(directory) / "results.csv")
            )
            self.assertFalse(panel.btn_pick_input.isEnabled())
            self.assertTrue(panel.btn_cancel.isEnabled())
            self.wait_until(lambda: not panel.is_running())

            self.assertIsInstance(captured["request"], GuiRunRequest)
            self.assertEqual(2, captured["request"].workers)
            self.assertEqual(17, captured["request"].checkpoint_every_cases)
            self.assertEqual("Completed", panel.progress.text())
            self.assertIn("[SAVE] checkpoint 1/2", panel.log.toPlainText())
            self.assertIn("[SAVE] final 2/2", panel.log.toPlainText())
            self.assertEqual(1, len(loaded))
            self.assertEqual("one", loaded[0][2]["case_id"])
            self.assertEqual([True], finished)
            self.assertIsNone(panel._run_worker)
            self.assertTrue(panel.btn_pick_input.isEnabled())
            self.assertFalse(panel.btn_cancel.isEnabled())

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
        rows = tuple(
            {"case_id": f"case_{index}", "out_dir": "outputs"} for index in range(7)
        )

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
            rows = ({"case_id": "one", "out_dir": str(vtp_path.parent)},)
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
                    "case_signature": [signatures["one"].primary.digest],
                }
            )
            panel = CasesPanel(
                fmf_solver_spec(adapters=adapters),
                artifact_reader=lambda _path: artifact,
            )
            panel.case_rows = rows
            panel.input_path = root / "cases.csv"
            panel._populate_case_table()
            viewer = _FakeViewer()
            window = MainWindow(panel.spec, cases_panel=panel, viewer_panel=viewer)

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

            # Manual inspection bypasses CasesPanel auto-load suppression.
            viewer.load_vtp(str(vtp_path))
            self.assertEqual(vtp_path.resolve(), viewer.loaded_path)

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
                panel.cancel_run()
                self.wait_until(
                    lambda active_panel=panel: not active_panel.is_running()
                )
                self.assertEqual("Canceled", panel.progress.text())
                self.assertIn("[CANCEL] Run canceled.", panel.log.toPlainText())
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
        self.assertIn("primary solver failure", panel.log.toPlainText())
        self.assertNotIn("Run canceled.", panel.log.toPlainText())

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
        viewer.save_selected_images_requested.emit()
        self.assertEqual([[rows[1]]], viewer.saved_rows)
        window.close()


if __name__ == "__main__":
    unittest.main()
