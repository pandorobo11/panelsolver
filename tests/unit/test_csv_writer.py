from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from panelsolver.app.csv_writer import (
    CSV_ENCODING,
    DURABLE_CSV_WRITE_POLICY,
    paths_collide,
    portable_path_key,
    write_csv_atomic,
)
from panelsolver.core import CsvProjection
from panelsolver.domains import fmf as fmf_csv
from panelsolver.domains import hypersonic as newt_csv
from panelsolver.domains.fmf import CANONICAL_CLI_POLICY as FMF_CLI_POLICY
from panelsolver.domains.fmf import GUI_ADAPTERS as FMF_GUI_ADAPTERS
from panelsolver.domains.hypersonic import CANONICAL_CLI_POLICY as NEWT_CLI_POLICY
from panelsolver.domains.hypersonic import GUI_ADAPTERS as NEWT_GUI_ADAPTERS


def projection() -> CsvProjection:
    return CsvProjection(
        ("case_id", "scope", "blank"),
        (
            {"case_id": "a", "scope": "total", "blank": None},
            {"case_id": "a", "scope": "component", "blank": None},
        ),
    )


def unicode_projection() -> CsvProjection:
    return CsvProjection(
        ("case_id", "note"),
        ({"case_id": "日本語ケース", "note": "日本語メモ"},),
    )


class CsvWriterTests(unittest.TestCase):
    def test_portable_path_key_handles_case_and_unicode_normalization(self) -> None:
        root = Path(tempfile.gettempdir()) / "portable-key" / "outputs"
        nfc = "caf\N{LATIN SMALL LETTER E WITH ACUTE}"
        nfd = "cafe\N{COMBINING ACUTE ACCENT}"
        collision_pairs = (
            (root / "case_a.vtp", root / "CASE_A.VTP"),
            (root / f"{nfc}.csv", root / f"{nfd}.csv"),
            (root / f"{nfc}.vtp", root / f"{nfd.upper()}.VTP"),
        )
        for first, second in collision_pairs:
            with self.subTest(first=first, second=second):
                self.assertEqual(portable_path_key(first), portable_path_key(second))
                self.assertTrue(paths_collide(first, second))

        self.assertFalse(paths_collide(root / "case_a.vtp", root / "case_b.vtp"))
        self.assertFalse(
            paths_collide(
                root / "first" / "case_a.vtp",
                root / "second" / "case_b.vtp",
            )
        )

    def test_products_use_one_durable_write_policy(self) -> None:
        self.assertIs(DURABLE_CSV_WRITE_POLICY, fmf_csv.CSV_WRITE_POLICY)
        self.assertIs(DURABLE_CSV_WRITE_POLICY, newt_csv.CSV_WRITE_POLICY)
        self.assertTrue(DURABLE_CSV_WRITE_POLICY.fsync_before_replace)

    def test_both_products_flush_fsync_replace_and_preserve_semantic_csv(self) -> None:
        for adapter in (fmf_csv, newt_csv):
            with (
                self.subTest(adapter=adapter.__name__),
                tempfile.TemporaryDirectory() as td,
            ):
                output = Path(td) / "results.csv"
                with (
                    patch("panelsolver.app.csv_writer.os.fsync") as fsync,
                    patch(
                        "panelsolver.app.csv_writer.os.replace",
                        wraps=os.replace,
                    ) as replace,
                ):
                    adapter.write_csv(output, projection())
                fsync.assert_called_once()
                replace.assert_called_once()
                self.assertEqual(b"\xef\xbb\xbf", output.read_bytes()[:3])
                with output.open(encoding=CSV_ENCODING, newline="") as handle:
                    reader = csv.DictReader(handle)
                    self.assertEqual(
                        [
                            {"case_id": "a", "scope": "total", "blank": ""},
                            {"case_id": "a", "scope": "component", "blank": ""},
                        ],
                        list(reader),
                    )

    def test_atomic_writer_emits_bom_and_round_trips_unicode(self) -> None:
        for adapter in (fmf_csv, newt_csv):
            with (
                self.subTest(adapter=adapter.__name__),
                tempfile.TemporaryDirectory() as td,
            ):
                output = Path(td) / "日本語-results.csv"
                adapter.write_csv(output, unicode_projection())
                self.assertEqual(b"\xef\xbb\xbf", output.read_bytes()[:3])
                with output.open(encoding=CSV_ENCODING, newline="") as handle:
                    self.assertEqual(
                        [{"case_id": "日本語ケース", "note": "日本語メモ"}],
                        list(csv.DictReader(handle)),
                    )

    def test_both_policies_preserve_output_and_clean_temp_on_failure(self) -> None:
        for policy in (fmf_csv.CSV_WRITE_POLICY, newt_csv.CSV_WRITE_POLICY):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as td:
                output = Path(td) / "results.csv"
                output.write_text("original\n", encoding="utf-8")
                with (
                    patch(
                        "panelsolver.app.csv_writer._write_projection",
                        side_effect=OSError("disk error"),
                    ),
                    self.assertRaisesRegex(OSError, "disk error"),
                ):
                    write_csv_atomic(output, projection(), policy)
                self.assertEqual("original\n", output.read_text(encoding="utf-8"))
                self.assertEqual([output], list(Path(td).iterdir()))

    def test_both_policies_clean_temp_on_replace_failure(self) -> None:
        for policy in (fmf_csv.CSV_WRITE_POLICY, newt_csv.CSV_WRITE_POLICY):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as td:
                output = Path(td) / "results.csv"
                output.write_text("original\n", encoding="utf-8")
                with (
                    patch(
                        "panelsolver.app.csv_writer.os.replace",
                        side_effect=OSError("replace error"),
                    ),
                    self.assertRaisesRegex(OSError, "replace error"),
                ):
                    write_csv_atomic(output, projection(), policy)
                self.assertEqual("original\n", output.read_text(encoding="utf-8"))
                self.assertEqual([output], list(Path(td).iterdir()))

    def test_both_policies_clean_temp_on_fsync_failure(self) -> None:
        for policy in (fmf_csv.CSV_WRITE_POLICY, newt_csv.CSV_WRITE_POLICY):
            with self.subTest(policy=policy), tempfile.TemporaryDirectory() as td:
                output = Path(td) / "results.csv"
                output.write_text("original\n", encoding="utf-8")
                with (
                    patch(
                        "panelsolver.app.csv_writer.os.fsync",
                        side_effect=OSError("fsync error"),
                    ),
                    self.assertRaisesRegex(OSError, "fsync error"),
                ):
                    write_csv_atomic(output, projection(), policy)
                self.assertEqual("original\n", output.read_text(encoding="utf-8"))
                self.assertEqual([output], list(Path(td).iterdir()))

    def test_collision_scope_is_shared_and_ignores_save_flags(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "cases.csv"
            stl_path = root / "mesh.stl"
            second_stl_path = root / "mesh-2.stl"
            out_dir = root / "outputs"
            case_rows = (
                {
                    "case_id": "case_a",
                    "stl_path": f"{stl_path};{second_stl_path}",
                    "out_dir": str(out_dir),
                    "save_vtp_on": 0,
                },
            )

            for adapter in (fmf_csv, newt_csv):
                for protected in (
                    input_path,
                    stl_path,
                    second_stl_path,
                    out_dir / "case_a.vtp",
                ):
                    with (
                        self.subTest(adapter=adapter.__name__, protected=protected),
                        self.assertRaisesRegex(ValueError, "protected path"),
                    ):
                        adapter.validate_results_output_path(
                            protected,
                            input_path,
                            case_rows,
                        )

    def test_relative_protected_paths_use_the_input_directory(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "project" / "cases.csv"
            rows = (
                {
                    "case_id": "case_a",
                    "stl_path": "geometry/mesh.stl",
                    "out_dir": "outputs",
                },
            )
            for adapter in (fmf_csv, newt_csv):
                for protected in (
                    input_path.parent / "geometry" / "mesh.stl",
                    input_path.parent / "outputs" / "case_a.vtp",
                ):
                    with (
                        self.subTest(
                            adapter=adapter.__name__,
                            protected=protected,
                        ),
                        self.assertRaisesRegex(ValueError, "protected path"),
                    ):
                        adapter.validate_results_output_path(
                            protected,
                            input_path,
                            rows,
                        )

    def test_both_products_reject_portable_summary_variants_with_roles(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "cases.csv"
            nfc = "caf\N{LATIN SMALL LETTER E WITH ACUTE}"
            nfd = "cafe\N{COMBINING ACUTE ACCENT}"
            stl_nfc = root / f"mesh-{nfc}.stl"
            cases = (
                (
                    root / "outputs" / "CASE_A.VTP",
                    input_path,
                    (
                        {
                            "case_id": "case_a",
                            "stl_path": str(root / "mesh.stl"),
                            "out_dir": str(root / "outputs"),
                            "save_vtp_on": 0,
                        },
                    ),
                    "planned VTP",
                    root / "outputs" / "case_a.vtp",
                ),
                (
                    root / "CASES.CSV",
                    input_path,
                    (
                        {
                            "case_id": "case_a",
                            "stl_path": str(root / "mesh.stl"),
                            "out_dir": str(root / "outputs"),
                        },
                    ),
                    "input",
                    input_path,
                ),
                (
                    root / f"mesh-{nfd}.stl",
                    input_path,
                    (
                        {
                            "case_id": "case_a",
                            "stl_path": str(stl_nfc),
                            "out_dir": str(root / "outputs"),
                        },
                    ),
                    "STL",
                    stl_nfc,
                ),
            )
            for adapter in (fmf_csv, newt_csv):
                for output, input_file, rows, role, protected in cases:
                    with self.subTest(adapter=adapter.__name__, role=role):
                        with self.assertRaises(ValueError) as caught:
                            adapter.validate_results_output_path(
                                output,
                                input_file,
                                rows,
                            )
                        message = str(caught.exception)
                        self.assertIn("summary path", message)
                        self.assertIn(f"{role} path", message)
                        self.assertIn(output.name, message)
                        self.assertIn(protected.name, message)
                        if role.startswith("planned") or role == "STL":
                            self.assertIn("case_id=", message)

    def test_existing_symlink_alias_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "cases.csv"
            input_path.write_text("case_id\n", encoding="utf-8")
            summary = root / "summary-symlink.csv"
            try:
                summary.symlink_to(input_path)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"symlink creation is unavailable: {exc}")
            for adapter in (fmf_csv, newt_csv):
                with self.assertRaises(ValueError) as caught:
                    adapter.validate_results_output_path(summary, input_path, ())
                self.assertIn("summary path", str(caught.exception))
                self.assertIn("input path", str(caught.exception))

    def test_existing_hardlink_alias_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "cases.csv"
            input_path.write_text("case_id\n", encoding="utf-8")
            summary = root / "summary-hardlink.csv"
            try:
                os.link(input_path, summary)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"hardlink creation is unavailable: {exc}")
            for adapter in (fmf_csv, newt_csv):
                with self.assertRaises(ValueError) as caught:
                    adapter.validate_results_output_path(summary, input_path, ())
                self.assertIn("summary path", str(caught.exception))
                self.assertIn("input path", str(caught.exception))

    def test_symlinked_planned_parent_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            real_out = root / "real-output"
            real_out.mkdir()
            linked_out = root / "linked-output"
            try:
                linked_out.symlink_to(real_out, target_is_directory=True)
            except (NotImplementedError, OSError) as exc:
                self.skipTest(f"directory symlink creation is unavailable: {exc}")
            rows = (
                {
                    "case_id": "case_a",
                    "stl_path": str(root / "mesh.stl"),
                    "out_dir": str(linked_out),
                    "save_vtp_on": 0,
                },
            )
            for adapter in (fmf_csv, newt_csv):
                with (
                    self.subTest(adapter=adapter.__name__),
                    self.assertRaisesRegex(
                        ValueError,
                        "planned VTP",
                    ),
                ):
                    adapter.validate_results_output_path(
                        real_out / "case_a.vtp",
                        root / "cases.csv",
                        rows,
                    )

    def test_planned_artifacts_are_validated_as_one_portable_set(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            nfc = "caf\N{LATIN SMALL LETTER E WITH ACUTE}"
            nfd = "cafe\N{COMBINING ACUTE ACCENT}"
            colliding_out_dirs = (
                (root / "Artifacts", root / "artifacts"),
                (root / nfc, root / nfd),
            )
            for first_out, second_out in colliding_out_dirs:
                rows = (
                    {
                        "case_id": "shared_case",
                        "stl_path": str(root / "mesh-a.stl"),
                        "out_dir": str(first_out),
                    },
                    {
                        "case_id": "shared_case",
                        "stl_path": str(root / "mesh-b.stl"),
                        "out_dir": str(second_out),
                    },
                )
                for adapter in (fmf_csv, newt_csv):
                    with (
                        self.subTest(
                            adapter=adapter.__name__,
                            first_out=first_out,
                            second_out=second_out,
                        ),
                        self.assertRaisesRegex(ValueError, "planned VTP"),
                    ):
                        adapter.validate_results_output_path(
                            root / "summary.csv",
                            root / "cases.csv",
                            rows,
                        )

            distinct_rows = (
                {
                    "case_id": "case_a",
                    "stl_path": str(root / "mesh.stl"),
                    "out_dir": str(root / "outputs"),
                },
                {
                    "case_id": "case_b",
                    "stl_path": str(root / "mesh.stl"),
                    "out_dir": str(root / "outputs"),
                },
            )
            expected = (root / "summary.csv").resolve()
            for adapter in (fmf_csv, newt_csv):
                self.assertEqual(
                    expected,
                    adapter.validate_results_output_path(
                        root / "summary.csv",
                        root / "cases.csv",
                        distinct_rows,
                    ),
                )

    def test_cli_and_gui_use_the_shared_collision_scope(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            input_path = root / "cases.csv"
            stl_path = root / "mesh.stl"
            artifact = root / "outputs" / "CASE_A.VTP"
            rows = (
                {
                    "case_id": "case_a",
                    "stl_path": str(stl_path),
                    "out_dir": str(root / "outputs"),
                    "save_vtp_on": 0,
                },
            )
            validators = (
                FMF_CLI_POLICY.validate_output_path,
                NEWT_CLI_POLICY.validate_output_path,
                FMF_GUI_ADAPTERS.validate_output_path,
                NEWT_GUI_ADAPTERS.validate_output_path,
            )
            for validator in validators:
                for protected in (input_path, stl_path, artifact):
                    with (
                        self.subTest(validator=validator, protected=protected),
                        self.assertRaisesRegex(ValueError, "protected path"),
                    ):
                        validator(protected, input_path, rows)


if __name__ == "__main__":
    unittest.main()
