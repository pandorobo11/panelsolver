from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from panelsolver.app.path_resolution import (
    auto_rename_path,
    default_image_filename,
    default_summary_output_path,
    resolve_batch_image_dir,
    resolve_case_image_dir,
    resolve_case_image_path,
    resolve_case_output_dir,
    resolve_case_vtp_path,
    resolve_input_relative_path,
    resolve_manual_vtp_image_path,
)
from tests.path_assertions import assert_paths_equivalent


class PathResolutionTests(unittest.TestCase):
    def test_relative_artifacts_share_the_input_table_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "project" / "input.csv"
            row = {"case_id": "case001", "out_dir": "outputs"}
            assert_paths_equivalent(
                self,
                input_path.parent / "outputs",
                resolve_case_output_dir(row, input_path),
            )
            assert_paths_equivalent(
                self,
                input_path.parent / "outputs" / "case001.vtp",
                resolve_case_vtp_path(row, input_path),
            )
            assert_paths_equivalent(
                self,
                input_path.parent / "outputs" / "input_result.csv",
                default_summary_output_path(input_path),
            )

    def test_absolute_output_directory_is_respected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            absolute = root / "shared-artifacts"
            input_path = root / "project" / "input.csv"
            assert_paths_equivalent(
                self,
                absolute,
                resolve_input_relative_path(absolute, input_path),
            )
            assert_paths_equivalent(
                self,
                absolute,
                resolve_case_output_dir(
                    {"case_id": "one", "out_dir": str(absolute)},
                    input_path,
                ),
            )

    def test_case_image_paths_preserve_output_directory_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "project" / "cases.xlsx"
            relative = {"case_id": "case_001", "out_dir": "results"}
            defaulted = {"case_id": "case_002", "out_dir": ""}
            absolute_dir = root / "shared"
            absolute = {"case_id": "case_003", "out_dir": str(absolute_dir)}

            assert_paths_equivalent(
                self,
                input_path.parent / "results" / "images",
                resolve_case_image_dir(relative, input_path),
            )
            assert_paths_equivalent(
                self,
                input_path.parent
                / "results"
                / "images"
                / "case_001__normal_traction_coeff.png",
                resolve_case_image_path(
                    relative,
                    input_path,
                    "normal_traction_coeff",
                ),
            )
            assert_paths_equivalent(
                self,
                input_path.parent / "outputs" / "images",
                resolve_case_image_dir(defaulted, input_path),
            )
            assert_paths_equivalent(
                self,
                absolute_dir / "images",
                resolve_case_image_dir(absolute, input_path),
            )

    def test_image_names_use_machine_field_and_manual_vtp_stem(self) -> None:
        self.assertEqual(
            "case_001__cp.png",
            default_image_filename("case_001", "cp"),
        )
        self.assertEqual(
            Path("/manual/images/sample__normal_traction_coeff.png"),
            resolve_manual_vtp_image_path(
                "/manual/sample.vtp",
                "normal_traction_coeff",
            ),
        )

    def test_batch_image_directory_is_common_or_input_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "project" / "cases.csv"
            common = (
                {"case_id": "one", "out_dir": "shared"},
                {"case_id": "two", "out_dir": "shared"},
            )
            mixed = (
                {"case_id": "one", "out_dir": "first"},
                {"case_id": "two", "out_dir": str(root / "second")},
            )
            assert_paths_equivalent(
                self,
                input_path.parent / "shared" / "images",
                resolve_batch_image_dir(common, input_path),
            )
            expected_mixed = input_path.parent / "outputs" / "images"
            assert_paths_equivalent(
                self,
                expected_mixed,
                resolve_batch_image_dir(mixed, input_path),
            )
            assert_paths_equivalent(
                self,
                expected_mixed,
                resolve_batch_image_dir(tuple(reversed(mixed)), input_path),
            )

    def test_auto_rename_avoids_existing_and_reserved_batch_paths(self) -> None:
        planned = Path("/captures/case_001__cp.png")
        existing = {
            planned,
            Path("/captures/case_001__cp_2.png"),
        }
        renamed = auto_rename_path(
            planned,
            path_exists=existing.__contains__,
        )
        self.assertEqual(Path("/captures/case_001__cp_3.png"), renamed)
        self.assertEqual(
            Path("/captures/case_001__cp_4.png"),
            auto_rename_path(
                planned,
                path_exists=existing.__contains__,
                reserved_paths={renamed},
            ),
        )


if __name__ == "__main__":
    unittest.main()
