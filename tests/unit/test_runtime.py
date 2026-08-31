from __future__ import annotations

import csv
import inspect
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import pytest
import pyvista as pv

from panelsolver.app import (
    DEFAULT_CHECKPOINT_CASES,
    GuiRunRequest,
    GuiRunResult,
    OutputKind,
    OutputPhase,
    prepare_product_cases,
    run_and_write_product_cases,
    run_product_cases,
)
from panelsolver.app.csv_writer import CSV_ENCODING, write_csv_atomic
from panelsolver.app.runtime import (
    _run_prepared_product_case as _real_run_prepared_product_case,
)
from panelsolver.core import (
    PartialResultPolicy,
    SchedulerCancelled,
    WorkerExecutionError,
    WorkerLogPolicy,
    case_execution_bucket_keys,
    clear_shielding_cache,
    shielding_cache_stats,
)
from panelsolver.domains.fmf import GUI_ADAPTERS as FMF_GUI_ADAPTERS
from panelsolver.domains.fmf import RUNTIME_POLICY as FMF_POLICY
from panelsolver.domains.fmf import read_cases as read_fmf_cases
from panelsolver.domains.fmf import run_cases as run_fmf_cases
from panelsolver.domains.hypersonic import RUNTIME_POLICY as NEWT_POLICY
from panelsolver.domains.hypersonic import read_cases as read_newt_cases
from panelsolver.domains.hypersonic import run_cases as run_newt_cases
from tests.current_case_fixtures import read_current_cases

INPUTS = Path(__file__).parents[1] / "fixtures" / "phase1" / "inputs"


def _fail_selected_prepared_case(prepared, logfn):
    if str(prepared.row["case_id"]).endswith("_bad"):
        raise RuntimeError("synthetic computation failure")
    return _real_run_prepared_product_case(prepared, logfn)


def _assert_artifact_semantics_equal(
    test_case: unittest.TestCase,
    actual_vtp: Path,
    expected_vtp: Path,
) -> None:
    actual_poly = pv.read(actual_vtp)
    expected_poly = pv.read(expected_vtp)
    test_case.assertEqual(expected_poly.points.dtype, actual_poly.points.dtype)
    np.testing.assert_array_equal(actual_poly.points, expected_poly.points)
    test_case.assertEqual(expected_poly.faces.dtype, actual_poly.faces.dtype)
    np.testing.assert_array_equal(actual_poly.faces, expected_poly.faces)
    for association in ("point_data", "cell_data", "field_data"):
        actual_data = getattr(actual_poly, association)
        expected_data = getattr(expected_poly, association)
        test_case.assertEqual(set(expected_data.keys()), set(actual_data.keys()))
        for name in expected_data:
            test_case.assertEqual(expected_data[name].dtype, actual_data[name].dtype)
            np.testing.assert_array_equal(actual_data[name], expected_data[name])


class RuntimeTests(unittest.TestCase):
    def _fmf_rows(self, root: Path, count: int) -> tuple[dict[str, object], ...]:
        base = (
            read_current_cases(read_fmf_cases, INPUTS / "fmfsolver_cases.csv")
            .iloc[0]
            .to_dict()
        )
        return tuple(
            {
                **base,
                "case_id": f"case_{index}",
                "out_dir": str(root / "vtp"),
                "save_vtp_on": 1,
            }
            for index in range(count)
        )

    def test_vtp_failure_keeps_case_projection_and_later_single_worker_cases(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rows = self._fmf_rows(root, 3)
            vtp_dir = root / "vtp"
            vtp_dir.mkdir()
            (vtp_dir / "case_1.vtp").mkdir()
            logs: list[str] = []

            result = run_and_write_product_cases(
                rows,
                FMF_POLICY,
                root / "summary.csv",
                workers=1,
                logfn=logs.append,
            )

            self.assertEqual(3, len(result.cases))
            self.assertEqual("", result.cases[1].vtp_path)
            self.assertTrue(result.cases[0].vtp_path)
            self.assertTrue(result.cases[2].vtp_path)
            self.assertEqual(
                ["case_0", "case_1", "case_2"],
                [
                    str(row["case_id"])
                    for row in result.csv.rows
                    if row["scope"] == "total"
                ],
            )
            self.assertEqual("", result.cases[1].csv.rows[0]["vtp_path"])
            self.assertEqual(1, len(result.output_issues))
            issue = result.output_issues[0]
            self.assertIs(OutputKind.VTP, issue.kind)
            self.assertIs(OutputPhase.WRITE, issue.phase)
            self.assertEqual("case_1", issue.case_id)
            self.assertTrue(result.summary_csv_saved)
            self.assertTrue(any("VTP output failed" in message for message in logs))

    @pytest.mark.slow
    def test_parallel_vtp_failures_are_aggregated_without_stopping_cases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rows = self._fmf_rows(root, 4)
            vtp_dir = root / "vtp"
            vtp_dir.mkdir()
            for case_id in ("case_1", "case_3"):
                (vtp_dir / f"{case_id}.vtp").mkdir()

            result = run_and_write_product_cases(
                rows,
                FMF_POLICY,
                root / "summary.csv",
                workers=2,
                checkpoint_every_cases=1,
            )

            self.assertEqual(4, len(result.cases))
            self.assertEqual(
                {"case_1", "case_3"},
                {
                    issue.case_id
                    for issue in result.output_issues
                    if issue.kind is OutputKind.VTP
                },
            )
            self.assertEqual(
                [True, False, True, False],
                [bool(case.vtp_path) for case in result.cases],
            )
            self.assertTrue(result.summary_csv_saved)

    def test_output_directory_failure_is_retained_without_stopping_cases(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rows = list(self._fmf_rows(root, 2))
            blocked_output = root / "blocked-output"
            blocked_output.write_text("not a directory\n", encoding="utf-8")
            rows[0]["out_dir"] = str(blocked_output)
            rows[1]["out_dir"] = str(root / "valid-output")

            result = run_and_write_product_cases(
                rows,
                FMF_POLICY,
                root / "summary.csv",
                workers=1,
            )

            self.assertEqual(
                ["case_0", "case_1"],
                [
                    str(row["case_id"])
                    for row in result.csv.rows
                    if row["scope"] == "total"
                ],
            )
            self.assertEqual("", result.cases[0].vtp_path)
            self.assertTrue(result.cases[1].vtp_path)
            self.assertTrue(result.summary_csv_saved)
            self.assertEqual(1, len(result.output_issues))
            issue = result.output_issues[0]
            self.assertIs(OutputKind.OUTPUT_DIRECTORY, issue.kind)
            self.assertIs(OutputPhase.PREPARE, issue.phase)
            self.assertEqual("case_0", issue.case_id)

    def test_final_summary_failure_is_output_issue_and_preserves_existing_csv(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rows = self._fmf_rows(root, 1)
            summary = root / "summary.csv"
            summary.write_bytes(b"existing-summary\n")
            with mock.patch(
                "panelsolver.app.runtime.write_csv_atomic",
                side_effect=OSError("summary denied"),
            ):
                result = run_and_write_product_cases(
                    rows,
                    FMF_POLICY,
                    summary,
                    checkpoint_every_cases=0,
                )

            self.assertEqual(1, len(result.cases))
            self.assertFalse(result.summary_csv_saved)
            self.assertEqual(b"existing-summary\n", summary.read_bytes())
            self.assertEqual(1, len(result.output_issues))
            issue = result.output_issues[0]
            self.assertIs(OutputKind.SUMMARY_CSV, issue.kind)
            self.assertIs(OutputPhase.FINAL, issue.phase)

    def test_checkpoint_summary_failure_is_retained_and_calculation_continues(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rows = self._fmf_rows(root, 3)
            summary = root / "summary.csv"
            calls = 0

            def fail_first_checkpoint(output, projection, policy):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise OSError("checkpoint denied")
                return write_csv_atomic(output, projection, policy)

            with mock.patch(
                "panelsolver.app.runtime.write_csv_atomic",
                side_effect=fail_first_checkpoint,
            ):
                result = run_and_write_product_cases(
                    rows,
                    FMF_POLICY,
                    summary,
                    checkpoint_every_cases=1,
                )

            self.assertEqual(3, len(result.cases))
            self.assertTrue(result.summary_csv_saved)
            self.assertEqual(1, len(result.output_issues))
            self.assertIs(OutputPhase.CHECKPOINT, result.output_issues[0].phase)
            with summary.open(encoding=CSV_ENCODING, newline="") as stream:
                saved = tuple(csv.DictReader(stream))
            self.assertEqual(
                ["case_0", "case_1", "case_2"],
                [row["case_id"] for row in saved if row["scope"] == "total"],
            )

    def test_complete_checkpoint_is_reused_as_final_summary(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rows = self._fmf_rows(root, 3)
            summary = root / "summary.csv"
            logs: list[str] = []

            with mock.patch(
                "panelsolver.app.runtime.write_csv_atomic",
                wraps=write_csv_atomic,
            ) as write:
                result = run_and_write_product_cases(
                    rows,
                    FMF_POLICY,
                    summary,
                    checkpoint_every_cases=len(rows),
                    log_snapshots=True,
                    logfn=logs.append,
                )

            self.assertEqual(1, write.call_count)
            self.assertTrue(result.summary_csv_saved)
            self.assertEqual((), result.output_issues)
            self.assertTrue(
                any("complete checkpoint reused" in message for message in logs)
            )
            with summary.open(encoding=CSV_ENCODING, newline="") as stream:
                saved = tuple(csv.DictReader(stream))
            self.assertEqual(
                ["case_0", "case_1", "case_2"],
                [row["case_id"] for row in saved if row["scope"] == "total"],
            )

    def test_partial_checkpoint_does_not_mask_final_summary_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rows = self._fmf_rows(root, 3)
            summary = root / "summary.csv"
            calls = 0

            def fail_final(output, projection, policy):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("final denied")
                return write_csv_atomic(output, projection, policy)

            with mock.patch(
                "panelsolver.app.runtime.write_csv_atomic",
                side_effect=fail_final,
            ):
                result = run_and_write_product_cases(
                    rows,
                    FMF_POLICY,
                    summary,
                    checkpoint_every_cases=2,
                )

            self.assertEqual(2, calls)
            self.assertFalse(result.summary_csv_saved)
            self.assertEqual(1, len(result.output_issues))
            self.assertIs(OutputPhase.FINAL, result.output_issues[0].phase)
            with summary.open(encoding=CSV_ENCODING, newline="") as stream:
                saved = tuple(csv.DictReader(stream))
            self.assertEqual(
                ["case_0", "case_1"],
                [row["case_id"] for row in saved if row["scope"] == "total"],
            )

    def test_checkpoint_default_is_shared_across_runtime_and_domains(self) -> None:
        for callback in (
            run_product_cases,
            run_and_write_product_cases,
            run_fmf_cases,
            run_newt_cases,
        ):
            with self.subTest(callback=callback):
                parameter = inspect.signature(callback).parameters[
                    "checkpoint_every_cases"
                ]
                self.assertEqual(DEFAULT_CHECKPOINT_CASES, parameter.default)

    def test_products_share_supported_scheduler_policy(self) -> None:
        for policy in (FMF_POLICY, NEWT_POLICY):
            with self.subTest(product=policy.product_id):
                self.assertIs(WorkerLogPolicy.FORWARD, policy.worker_log_policy)
                self.assertIs(
                    PartialResultPolicy.YIELD_COMPLETED,
                    policy.partial_result_policy,
                )

    def test_single_worker_groups_exact_reuse_buckets_without_output_reordering(
        self,
    ) -> None:
        base = (
            read_current_cases(read_fmf_cases, INPUTS / "fmfsolver_cases.csv")
            .iloc[0]
            .to_dict()
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            common = {
                **base,
                "out_dir": temp_dir,
                "save_vtp_on": 0,
                "shielding_on": 1,
                "ray_backend": "rtree",
                "attitude_input": "beta_tan",
                "alpha_deg": 0.0,
            }
            rows = (
                {**common, "case_id": "A-1", "beta_or_bank_deg": 0.0},
                {**common, "case_id": "B", "beta_or_bank_deg": 4.0e-13},
                {**common, "case_id": "A-2", "beta_or_bank_deg": 0.0},
            )
            prepared = prepare_product_cases(rows, FMF_POLICY)
            requests = tuple(case.adapted.request for case in prepared)
            self.assertEqual(
                round(requests[0].common_case.beta_t_deg, 12),
                round(requests[1].common_case.beta_t_deg, 12),
            )
            self.assertFalse(
                np.array_equal(
                    requests[0].velocity_hat_stl,
                    requests[1].velocity_hat_stl,
                )
            )
            bucket_keys = case_execution_bucket_keys(requests)
            self.assertEqual(bucket_keys[0], bucket_keys[2])
            self.assertNotEqual(bucket_keys[0], bucket_keys[1])

            logs: list[str] = []
            progress: list[tuple[int, int]] = []
            snapshots: list[list[str]] = []

            def capture(projection, _done: int, _total: int, _final: bool) -> None:
                snapshots.append(
                    [
                        str(row["case_id"])
                        for row in projection.rows
                        if row["scope"] == "total"
                    ]
                )

            clear_shielding_cache()
            result = run_fmf_cases(
                rows,
                workers=1,
                logfn=logs.append,
                progress_cb=lambda done, total: progress.append((done, total)),
                checkpoint_every_cases=1,
                snapshot_cb=capture,
            )

        execution_ids = [
            message.rsplit("case_id=", 1)[1]
            for message in logs
            if message.startswith("[RUN] (")
        ]
        self.assertEqual(["A-1", "A-2", "B"], execution_ids)
        self.assertEqual(
            ["A-1", "B", "A-2"],
            [str(case.csv.rows[0]["case_id"]) for case in result.cases],
        )
        self.assertEqual([(1, 3), (2, 3), (3, 3)], progress)
        input_positions = {"A-1": 0, "B": 1, "A-2": 2}
        for snapshot in snapshots:
            self.assertEqual(
                sorted(snapshot, key=input_positions.__getitem__),
                snapshot,
            )
        self.assertEqual(["A-1", "B", "A-2"], snapshots[-1])
        self.assertEqual(1, shielding_cache_stats().mask_hits)

    def test_artifacts_off_still_creates_directory_and_blank_csv_paths(self) -> None:
        products = (
            (read_fmf_cases, "fmfsolver_cases.csv", FMF_POLICY),
            (read_newt_cases, "newtsolver_cases.csv", NEWT_POLICY),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for reader, filename, policy in products:
                row = read_current_cases(reader, INPUTS / filename).iloc[0].to_dict()
                out_dir = root / policy.product_id / "case_outputs"
                row.update(out_dir=str(out_dir), save_vtp_on=0)
                summary = root / policy.product_id / "summary.csv"
                result = run_and_write_product_cases((row,), policy, summary)
                with self.subTest(product=policy.product_id):
                    self.assertTrue(out_dir.is_dir())
                    self.assertFalse((out_dir / f"{row['case_id']}.vtp").exists())
                    self.assertFalse((out_dir / f"{row['case_id']}.npz").exists())
                    self.assertEqual("", result.cases[0].vtp_path)
                    self.assertFalse(hasattr(result.cases[0], "npz_path"))
                    with summary.open(encoding=CSV_ENCODING, newline="") as stream:
                        total = next(csv.DictReader(stream))
                    self.assertEqual("", total["vtp_path"])
                    self.assertNotIn("save_npz_on", total)
                    self.assertNotIn("npz_path", total)

    def test_checkpoints_are_completed_snapshots_in_input_order(self) -> None:
        frame = read_current_cases(read_fmf_cases, INPUTS / "fmfsolver_cases.csv").iloc[
            [0, 1, 4]
        ]
        snapshots: list[tuple[list[str], int, bool]] = []

        def capture(projection, done: int, _total: int, final: bool) -> None:
            case_ids = [
                str(row["case_id"])
                for row in projection.rows
                if row["scope"] == "total"
            ]
            snapshots.append((case_ids, done, final))

        with tempfile.TemporaryDirectory() as temp_dir:
            frame["out_dir"] = temp_dir
            rows = tuple(frame.to_dict(orient="records"))
            run_fmf_cases(
                rows,
                workers=1,
                checkpoint_every_cases=1,
                snapshot_cb=capture,
            )
        input_order = {str(row["case_id"]): index for index, row in enumerate(rows)}
        self.assertEqual([1, 2, 3, 3], [done for _, done, _ in snapshots])
        self.assertEqual(
            [False, False, False, True], [final for _, _, final in snapshots]
        )
        for case_ids, _, _ in snapshots:
            self.assertEqual(
                sorted(case_ids, key=input_order.__getitem__),
                case_ids,
            )
        self.assertEqual(
            [str(row["case_id"]) for row in rows],
            snapshots[-1][0],
        )

    def test_initial_cancellation_has_no_case_side_effect(self) -> None:
        row = (
            read_current_cases(read_fmf_cases, INPUTS / "fmfsolver_cases.csv")
            .iloc[0]
            .to_dict()
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "not-created"
            row["out_dir"] = str(out_dir)
            with self.assertRaises(SchedulerCancelled):
                run_fmf_cases((row,), cancel_cb=lambda: True)
            self.assertFalse(out_dir.exists())

    @pytest.mark.slow
    def test_failed_chunk_policy_controls_checkpoint_logs_and_partial_result(
        self,
    ) -> None:
        products = (
            ("fmfsolver", read_fmf_cases, "fmfsolver_cases.csv", FMF_POLICY),
            ("newtsolver", read_newt_cases, "newtsolver_cases.csv", NEWT_POLICY),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for product_id, reader, filename, policy in products:
                with self.subTest(product=product_id):
                    product_root = root / product_id
                    product_root.mkdir()
                    case_output = product_root / "case-output"
                    summary = product_root / "summary.csv"
                    summary.write_bytes(b"pre-existing summary is replaced\n")

                    base = (
                        read_current_cases(reader, INPUTS / filename).iloc[0].to_dict()
                    )
                    good_a = dict(base)
                    good_b = dict(base)
                    bad = dict(base)
                    good_ids = (
                        f"{product_id}_good_a",
                        f"{product_id}_good_b",
                    )
                    bad_id = f"{product_id}_bad"
                    for good, good_id in zip((good_a, good_b), good_ids, strict=True):
                        good.update(
                            case_id=good_id,
                            shielding_on=1,
                            ray_backend="rtree",
                            out_dir=str(case_output),
                            save_vtp_on=1,
                        )
                    bad.update(
                        case_id=bad_id,
                        shielding_on=1,
                        ray_backend="rtree",
                        out_dir=str(case_output),
                        save_vtp_on=1,
                    )
                    logs: list[str] = []
                    progress: list[tuple[int, int]] = []

                    with (
                        mock.patch.dict(
                            os.environ,
                            {"PANELSOLVER_PARALLEL_CHUNK_CASES": "3"},
                        ),
                        mock.patch(
                            "panelsolver.app.runtime._run_prepared_product_case",
                            new=_fail_selected_prepared_case,
                        ),
                    ):
                        with self.assertRaises(WorkerExecutionError) as caught:
                            run_and_write_product_cases(
                                (good_a, good_b, bad),
                                policy,
                                summary,
                                workers=2,
                                logfn=logs.append,
                                progress_cb=lambda done, total, sink=progress: (
                                    sink.append((done, total))
                                ),
                                checkpoint_every_cases=1,
                                log_snapshots=True,
                            )

                    self.assertIn(
                        "synthetic computation failure",
                        caught.exception.remote_traceback,
                    )
                    for good_id in good_ids:
                        self.assertTrue((case_output / f"{good_id}.vtp").is_file())
                    self.assertEqual([], list(case_output.glob("*.npz")))
                    self.assertFalse((case_output / f"{bad_id}.vtp").exists())
                    self.assertFalse(any("[SAVE] final" in message for message in logs))

                    reference_output = product_root / "reference-output"
                    reference_good = dict(good_a, out_dir=str(reference_output))
                    run_and_write_product_cases(
                        (reference_good,),
                        policy,
                        product_root / "reference-summary.csv",
                    )
                    _assert_artifact_semantics_equal(
                        self,
                        case_output / f"{good_ids[0]}.vtp",
                        reference_output / f"{good_ids[0]}.vtp",
                    )

                    self.assertEqual([(1, 3), (2, 3)], progress)
                    with summary.open(encoding=CSV_ENCODING, newline="") as stream:
                        rows = tuple(csv.DictReader(stream))
                    self.assertEqual(
                        list(good_ids),
                        [row["case_id"] for row in rows if row["scope"] == "total"],
                    )
                    self.assertFalse(any(row["case_id"] == bad_id for row in rows))
                    self.assertTrue(
                        any("[SAVE] checkpoint 2/3" in message for message in logs)
                    )
                    self.assertTrue(any("[OK] (2/3)" in message for message in logs))
                    self.assertTrue(
                        any(message.startswith("[WARN]") for message in logs)
                    )

    @pytest.mark.slow
    def test_parallel_success_is_input_ordered_and_forwards_worker_logs(self) -> None:
        products = (
            (
                read_current_cases(read_fmf_cases, INPUTS / "fmfsolver_cases.csv").iloc[
                    [0, 1]
                ],
                run_fmf_cases,
                True,
            ),
            (
                read_current_cases(
                    read_newt_cases, INPUTS / "newtsolver_cases.csv"
                ).iloc[[0, 1]],
                run_newt_cases,
                True,
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            for product_index, (frame, runner, forwards_worker_logs) in enumerate(
                products
            ):
                with self.subTest(runner=runner.__module__):
                    out_dir = Path(temp_dir) / str(product_index)
                    frame = frame.copy()
                    frame["out_dir"] = str(out_dir)
                    rows = tuple(frame.to_dict(orient="records"))
                    logs: list[str] = []
                    result = runner(rows, workers=2, logfn=logs.append)
                    self.assertEqual(
                        [str(row["case_id"]) for row in rows],
                        [str(case.csv.rows[0]["case_id"]) for case in result.cases],
                    )
                    self.assertEqual(
                        forwards_worker_logs,
                        any(message.startswith("[WARN]") for message in logs),
                    )

    def test_real_gui_adapters_read_run_write_and_return_first_artifact(self) -> None:
        rows = tuple(
            read_current_cases(read_fmf_cases, INPUTS / "fmfsolver_cases.csv").to_dict(
                orient="records"
            )
        )
        self.assertEqual(6, len(rows))
        with tempfile.TemporaryDirectory() as temp_dir:
            row = dict(rows[0])
            row["out_dir"] = temp_dir
            output = Path(temp_dir) / "summary.csv"
            logs: list[str] = []
            progress: list[tuple[int, int]] = []
            result = FMF_GUI_ADAPTERS.run_cases(
                GuiRunRequest(
                    rows=(row,),
                    workers=1,
                    checkpoint_every_cases=DEFAULT_CHECKPOINT_CASES,
                    output_path=output,
                    log=logs.append,
                    progress=lambda done, total: progress.append((done, total)),
                    cancel_requested=lambda: False,
                )
            )
            self.assertTrue(output.exists())
            self.assertEqual(
                Path(temp_dir) / "fmf_zero_plate.vtp", result.first_vtp_path
            )
            self.assertEqual("fmf_zero_plate", result.first_case_row["case_id"])
            self.assertEqual([(1, 1)], progress)
            self.assertTrue(any("[SAVE] final" in message for message in logs))
            self.assertEqual(
                FMF_GUI_ADAPTERS.build_case_signature(row).digest,
                FMF_GUI_ADAPTERS.build_case_signature(result.first_case_row).digest,
            )

    def test_gui_checkpoint_value_reaches_domain_runtime(self) -> None:
        row = (
            read_current_cases(read_fmf_cases, INPUTS / "fmfsolver_cases.csv")
            .iloc[0]
            .to_dict()
        )
        batch = object()
        with (
            mock.patch(
                "panelsolver.domains.fmf.run_and_write_product_cases",
                return_value=batch,
            ) as run,
            mock.patch(
                "panelsolver.domains.fmf.gui_run_result_from_batch",
                return_value=GuiRunResult(),
            ),
        ):
            FMF_GUI_ADAPTERS.run_cases(
                GuiRunRequest(
                    rows=(row,),
                    workers=1,
                    checkpoint_every_cases=0,
                    output_path=Path("summary.csv"),
                    log=lambda _message: None,
                    progress=lambda _done, _total: None,
                    cancel_requested=lambda: False,
                )
            )
        self.assertEqual(0, run.call_args.kwargs["checkpoint_every_cases"])


if __name__ == "__main__":
    unittest.main()
