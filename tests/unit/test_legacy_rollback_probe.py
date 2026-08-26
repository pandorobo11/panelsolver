import csv
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from panelsolver.app.csv_writer import CSV_ENCODING
from scripts.probe_legacy_rollback import (
    LEGACY_SPECS,
    _archive_commit,
    _prepare_panel_wheel,
    _run_sample,
    _stage_current_panel_inputs,
    sha256_file,
)

ROOT = Path(__file__).parents[2]


class LegacyRollbackProbeTests(unittest.TestCase):
    def test_sample_uses_generation_specific_checkpoint_cli_option(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_path = root / "cases.csv"
            input_path.write_text("case_id\ncase-a\n", encoding="utf-8")
            for legacy_cli, expected, rejected in (
                (True, "--flush-every-cases", "--checkpoint-every-cases"),
                (False, "--checkpoint-every-cases", "--flush-every-cases"),
            ):
                with self.subTest(legacy_cli=legacy_cli):
                    output = root / f"results-{legacy_cli}.csv"
                    output.write_text(
                        "case_id,CA,CY,CN,Cl,Cm,Cn,CD,CL\ncase-a,0,0,0,0,0,0,0,0\n",
                        encoding="utf-8",
                    )
                    with patch("scripts.probe_legacy_rollback._run") as run:
                        _run_sample(
                            root / "python",
                            "fmfsolver",
                            input_path,
                            "case-a",
                            output,
                            {},
                            legacy_cli=legacy_cli,
                        )
                    command = run.call_args.args[0]
                    self.assertIn(expected, command)
                    self.assertNotIn(rejected, command)

    def test_pins_match_migration_sources(self) -> None:
        migration_sources = (
            ROOT / "devdocs" / "history" / "migration" / "MIGRATION_SOURCES.md"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            {"fmfsolver", "newtsolver"},
            {spec.name for spec in LEGACY_SPECS},
        )
        for spec in LEGACY_SPECS:
            with self.subTest(product=spec.name):
                self.assertIn(spec.repository.removesuffix(".git"), migration_sources)
                self.assertIn(spec.commit, migration_sources)

    def test_sha256_is_content_sensitive(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "artifact.whl"
            path.write_bytes(b"first")
            first = sha256_file(path)
            path.write_bytes(b"second")
            self.assertNotEqual(first, sha256_file(path))

    def test_archive_refuses_a_commit_other_than_the_exact_pin(self) -> None:
        spec = LEGACY_SPECS[0]
        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch(
                "scripts.probe_legacy_rollback._git",
                return_value="0" * 40,
            ),
            self.assertRaisesRegex(RuntimeError, "commit mismatch"),
        ):
            _archive_commit(
                Path(temp_dir),
                spec,
                Path(temp_dir) / "archive",
            )

    def test_supplied_panel_wheel_is_copied_exactly_without_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repository = root / "repository"
            repository.mkdir()
            (repository / "pyproject.toml").write_text(
                '[project]\nname = "panelsolver"\nversion = "2.3.4"\n',
                encoding="utf-8",
            )
            supplied = root / "download" / "panelsolver-2.3.4-py3-none-any.whl"
            supplied.parent.mkdir()
            with zipfile.ZipFile(supplied, "w") as archive:
                archive.writestr(
                    "panelsolver-2.3.4.dist-info/METADATA",
                    "Metadata-Version: 2.4\nName: panelsolver\nVersion: 2.3.4\n",
                )

            with patch("scripts.probe_legacy_rollback._run") as run:
                selected = _prepare_panel_wheel(
                    repository,
                    root / "artifacts" / "panelsolver",
                    supplied,
                )

            run.assert_not_called()
            self.assertEqual(supplied.name, selected.name)
            self.assertEqual(sha256_file(supplied), sha256_file(selected))

    def test_current_panel_inputs_are_staged_without_mutating_history(self) -> None:
        source = ROOT / "tests" / "fixtures" / "phase1" / "inputs"
        source_csv = source / "fmfsolver_cases.csv"
        with source_csv.open(encoding=CSV_ENCODING, newline="") as stream:
            self.assertIn("save_npz_on", csv.DictReader(stream).fieldnames or ())

        with tempfile.TemporaryDirectory() as temp_dir:
            staged = _stage_current_panel_inputs(ROOT, Path(temp_dir))
            with (staged / "fmfsolver_cases.csv").open(
                encoding=CSV_ENCODING, newline=""
            ) as stream:
                self.assertNotIn(
                    "save_npz_on",
                    csv.DictReader(stream).fieldnames or (),
                )
            self.assertTrue((staged / "stl" / "plate.stl").is_file())

        with source_csv.open(encoding=CSV_ENCODING, newline="") as stream:
            self.assertIn("save_npz_on", csv.DictReader(stream).fieldnames or ())


if __name__ == "__main__":
    unittest.main()
