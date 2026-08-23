from __future__ import annotations

import hashlib
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets

from fmfsolver._frontend import _legacy_gui_spec as fmf_solver_spec
from newtsolver._frontend import _legacy_gui_spec as newt_solver_spec
from panelsolver.app import (
    DEFAULT_CHECKPOINT_CASES,
    ArtifactSignatureCandidates,
    GuiRunResult,
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
            validator
            if validator is not None
            else lambda out, _input, _rows: Path(out)
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
        self.assertEqual(["case_b", "case_a"], [r["case_id"] for r in panel.selected_or_all_case_rows()])
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
        self.assertEqual(["case_b", "case_a"], [r["case_id"] for r in panel.selected_case_rows()])

    def test_automatic_artifact_requires_current_signature_and_clears_otherwise(self) -> None:
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
            panel.vtp_loaded.connect(lambda *args: loaded.append(args))
            panel.viewer_clear_requested.connect(lambda: cleared.append(True))
            panel.case_table.selectRow(0)
            self.assertEqual(1, len(loaded))
            self.assertEqual("case_b", loaded[0][2]["case_id"])

            stale = _signature("stale")
            current.field_data["case_signature"] = [stale.digest]
            panel.on_case_selection_changed()
            self.assertTrue(cleared)
            panel.case_table.clearSelection()
            self.assertGreaterEqual(len(cleared), 2)

    def test_automatic_artifact_resolves_relative_out_dir_from_input_parent(self) -> None:
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
            panel.viewer_clear_requested.connect(lambda: cleared.append(True))
            panel.case_table.selectRow(0)
            self.assertTrue(cleared)
            Path(directory, "case_b.vtp").write_text("fixture", encoding="utf-8")
            panel._artifact_reader = lambda _path: (_ for _ in ()).throw(ValueError("broken"))
            panel.on_case_selection_changed()
            self.assertIn("Failed to read VTP", panel.log.toPlainText())

    def test_validation_failure_clears_prior_state_and_shows_structured_issues(self) -> None:
        panel, _ = self.make_panel()
        panel.load_input_file("/tmp/good.csv")

        def read_invalid(_path):
            raise StructuredError()

        failing_spec = fmf_solver_spec(
            adapters=_adapters((), {}, reader=read_invalid)
        )
        panel.spec = failing_spec
        with patch.object(ValidationIssuesDialog, "exec", return_value=0) as show:
            self.assertFalse(panel.load_input_file("/tmp/bad.csv"))
        show.assert_called_once()
        self.assertEqual((), panel.case_rows)
        self.assertIsNone(panel.input_path)
        self.assertEqual(0, panel.case_table.rowCount())
        self.assertFalse(panel.btn_run.isEnabled())

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

            with patch.object(QtWidgets.QFileDialog, "getSaveFileName", side_effect=choose):
                panel.request_run()
            self.wait_until(lambda: not panel.is_running())
            self.assertEqual(
                Path(directory) / "outputs" / "cases_result.csv",
                captured["default"],
            )
            self.assertTrue(captured["dir_existed"])
            self.assertEqual(["case_b", "case_a"], [r["case_id"] for r in emitted[0][0]])
            self.assertEqual(1, emitted[0][1])
            self.assertEqual(37, emitted[0][2])
            self.assertEqual(Path(directory) / "result.csv", emitted[0][3])

    def test_checkpoint_spinbox_defaults_and_accepts_zero(self) -> None:
        panel, _ = self.make_panel()
        self.assertEqual(
            DEFAULT_CHECKPOINT_CASES,
            panel.spin_checkpoint_every_cases.value(),
        )
        self.assertEqual(0, panel.spin_checkpoint_every_cases.minimum())
        panel.spin_checkpoint_every_cases.setValue(0)
        self.assertEqual(0, panel.spin_checkpoint_every_cases.value())

    def test_run_cancel_and_output_rejection_do_not_emit(self) -> None:
        def reject(_out, _input, _rows):
            raise ValueError("collision")

        panel, _ = self.make_panel(validator=reject)
        panel.load_input_file("/tmp/cases.csv")
        emitted: list[tuple] = []
        panel.run_requested.connect(lambda *args: emitted.append(args))
        with patch.object(QtWidgets.QFileDialog, "getSaveFileName", return_value=("", "")):
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
