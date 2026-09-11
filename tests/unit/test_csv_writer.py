from __future__ import annotations

import csv
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from panelsolver.app.csv_writer import (
    CSV_ENCODING,
    CsvAppendRollbackError,
    append_csv,
    paths_collide,
    portable_path_key,
    write_csv_atomic,
)
from panelsolver.core import CsvProjection
from panelsolver.domains import fmf as fmf_csv
from panelsolver.domains import hypersonic as hypersonic_csv
from panelsolver.domains.fmf import CLI_POLICY as FMF_CLI_POLICY
from panelsolver.domains.fmf import GUI_ADAPTERS as FMF_GUI_ADAPTERS
from panelsolver.domains.hypersonic import CLI_POLICY as HYPERSONIC_CLI_POLICY
from panelsolver.domains.hypersonic import GUI_ADAPTERS as HYPERSONIC_GUI_ADAPTERS


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
    def test_append_preserves_header_bom_and_quoted_unicode_cells(self) -> None:
        first = CsvProjection(
            ("case_id", 'extra\n"column"'),
            ({"case_id": "日本語", 'extra\n"column"': 'note,\n"quoted"'},),
        )
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "results.csv"
            write_csv_atomic(output, first)
            with patch("panelsolver.app.csv_writer.os.fsync", wraps=os.fsync) as sync:
                for _ in range(2):
                    append_csv(output, first)
            self.assertEqual(2, sync.call_count)
            self.assertEqual(1, output.read_bytes().count(b"\xef\xbb\xbf"))
            with output.open(encoding=CSV_ENCODING, newline="") as handle:
                self.assertEqual(
                    [dict(first.rows[0])] * 3, list(csv.DictReader(handle))
                )

    def test_append_rejects_missing_file_or_changed_columns(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "results.csv"
            with self.assertRaises(FileNotFoundError):
                append_csv(output, projection())
            self.assertFalse(output.exists())
            write_csv_atomic(output, projection())
            before = output.read_bytes()
            with self.assertRaisesRegex(ValueError, "columns"):
                append_csv(output, unicode_projection())
            self.assertEqual(before, output.read_bytes())

    def test_partial_append_or_sync_failure_rolls_back_and_can_retry(self) -> None:
        real_write = os.write

        def partial_failure(descriptor, payload):
            real_write(descriptor, payload[:7])
            raise OSError("partial write")

        for failure in ("write", "fsync"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as td:
                output = Path(td) / "results.csv"
                write_csv_atomic(output, projection())
                before = output.read_bytes()
                target = f"panelsolver.app.csv_writer.os.{failure}"
                effect = (
                    partial_failure if failure == "write" else [OSError("sync"), None]
                )
                with patch(target, side_effect=effect), self.assertRaises(OSError):
                    append_csv(output, projection())
                self.assertEqual(before, output.read_bytes())
                append_csv(output, projection())
                with output.open(encoding=CSV_ENCODING, newline="") as handle:
                    self.assertEqual(4, len(list(csv.DictReader(handle))))

    def test_short_writes_are_completed(self) -> None:
        real_write = os.write
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "results.csv"
            write_csv_atomic(output, unicode_projection())
            with patch(
                "panelsolver.app.csv_writer.os.write",
                side_effect=lambda fd, payload: real_write(fd, payload[:3]),
            ):
                append_csv(output, unicode_projection())
            with output.open(encoding=CSV_ENCODING, newline="") as handle:
                self.assertEqual(
                    [dict(unicode_projection().rows[0])] * 2,
                    list(csv.DictReader(handle)),
                )

    def test_rollback_truncate_or_sync_failure_is_distinct(self) -> None:
        for failure in ("ftruncate", "fsync"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as td:
                output = Path(td) / "results.csv"
                write_csv_atomic(output, projection())
                with (
                    patch(
                        "panelsolver.app.csv_writer.os.write",
                        side_effect=OSError("write"),
                    ),
                    patch(
                        f"panelsolver.app.csv_writer.os.{failure}",
                        side_effect=OSError("rollback"),
                    ),
                    self.assertRaisesRegex(CsvAppendRollbackError, "rollback failed"),
                ):
                    append_csv(output, projection())

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

    def test_atomic_writer_syncs_complete_csv_then_closes_before_replacement(
        self,
    ) -> None:
        real_temporary_file = tempfile.NamedTemporaryFile
        real_fsync = os.fsync
        real_replace = os.replace
        handles = []
        events = []
        contents = CsvProjection(
            ("case_id", "scope", "blank"),
            (
                {"case_id": "日本語", "scope": "total", "blank": None},
                {"case_id": "日本語", "scope": "component", "blank": None},
            ),
        )
        expected = [
            {"case_id": "日本語", "scope": "total", "blank": ""},
            {"case_id": "日本語", "scope": "component", "blank": ""},
        ]

        def assert_complete_csv(path):
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            with path.open(encoding="utf-8-sig", newline="") as handle:
                self.assertEqual(expected, list(csv.DictReader(handle)))

        def temporary_file(**kwargs):
            handle = real_temporary_file(**kwargs)
            handles.append(handle)
            return handle

        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "日本語-results.csv"
            output.write_bytes(b"previous run\n")

            def sync(descriptor):
                handle = handles[0]
                self.assertFalse(handle.closed)
                self.assertEqual(handle.fileno(), descriptor)
                assert_complete_csv(Path(handle.name))
                self.assertEqual(b"previous run\n", output.read_bytes())
                events.append("sync")
                real_fsync(descriptor)

            def replace(source, destination):
                self.assertTrue(handles[0].closed)
                self.assertEqual(["sync"], events)
                self.assertEqual(b"previous run\n", output.read_bytes())
                events.append("replace")
                real_replace(source, destination)

            with (
                patch(
                    "panelsolver.app.csv_writer.tempfile.NamedTemporaryFile",
                    side_effect=temporary_file,
                ),
                patch("panelsolver.app.csv_writer.os.fsync", side_effect=sync),
                patch("panelsolver.app.csv_writer.os.replace", side_effect=replace),
            ):
                write_csv_atomic(output, contents)
            self.assertEqual(["sync", "replace"], events)
            assert_complete_csv(output)
            self.assertEqual([output], list(Path(td).iterdir()))

    def test_atomic_writer_preserves_output_and_cleans_temp_on_failure(self) -> None:
        for target, message in (
            ("_write_projection", "disk error"),
            ("os.replace", "replace error"),
            ("os.fsync", "fsync error"),
        ):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as td:
                output = Path(td) / "results.csv"
                output.write_text("original\n", encoding="utf-8")
                with (
                    patch(
                        f"panelsolver.app.csv_writer.{target}",
                        side_effect=OSError(message),
                    ),
                    self.assertRaisesRegex(OSError, message),
                ):
                    write_csv_atomic(output, projection())
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

            for adapter in (fmf_csv, hypersonic_csv):
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
            for adapter in (fmf_csv, hypersonic_csv):
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
            for adapter in (fmf_csv, hypersonic_csv):
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
            for adapter in (fmf_csv, hypersonic_csv):
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
            for adapter in (fmf_csv, hypersonic_csv):
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
            for adapter in (fmf_csv, hypersonic_csv):
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
                for adapter in (fmf_csv, hypersonic_csv):
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
            for adapter in (fmf_csv, hypersonic_csv):
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
                HYPERSONIC_CLI_POLICY.validate_output_path,
                FMF_GUI_ADAPTERS.validate_output_path,
                HYPERSONIC_GUI_ADAPTERS.validate_output_path,
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
