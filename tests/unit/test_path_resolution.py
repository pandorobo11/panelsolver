from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from panelsolver.app.path_resolution import (
    auto_rename_path,
    default_image_filename,
    default_summary_output_path,
    resolve_case_image_path,
    resolve_case_vtp_path,
    resolve_image_dir,
    resolve_input_relative_path,
    resolve_manual_vtp_image_path,
    resolve_output_dir,
)
from tests.path_assertions import assert_paths_equivalent


class PathResolutionTests(unittest.TestCase):
    def test_relative_artifacts_share_the_input_table_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "project" / "input.csv"
            row = {"case_id": "case001"}
            assert_paths_equivalent(
                self,
                input_path.parent / "outputs",
                resolve_output_dir(input_path),
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

    def test_absolute_input_relative_path_is_respected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            absolute = root / "shared-artifacts"
            input_path = root / "project" / "input.csv"
            assert_paths_equivalent(
                self,
                absolute,
                resolve_input_relative_path(absolute, input_path),
            )

    def test_case_images_use_the_input_relative_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "project" / "cases.xlsx"
            assert_paths_equivalent(
                self,
                input_path.parent / "outputs" / "images",
                resolve_image_dir(input_path),
            )
            assert_paths_equivalent(
                self,
                input_path.parent
                / "outputs"
                / "images"
                / "case_001__normal_traction_coeff.png",
                resolve_case_image_path(
                    {"case_id": "case_001"},
                    input_path,
                    "normal_traction_coeff",
                ),
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

    def test_image_filename_components_are_portable_and_have_fallbacks(self) -> None:
        for unsafe in '/\\:*?"<>|':
            with self.subTest(unsafe=unsafe):
                self.assertEqual(
                    "case__cp_raw.png",
                    default_image_filename("case", f"cp{unsafe}raw"),
                )
        self.assertEqual(
            "case_001__normal_traction_coeff.png",
            default_image_filename(" case/001. ", "normal_traction_coeff"),
        )
        self.assertEqual(
            "image__scalar.png",
            default_image_filename(" . ", "  "),
        )
        self.assertEqual(
            Path("manual/images/sample_raw__cp_raw.png"),
            resolve_manual_vtp_image_path(
                Path("manual") / "sample?raw.vtp",
                "cp:raw",
            ),
        )

    def test_auto_rename_avoids_existing_and_reserved_batch_paths(self) -> None:
        planned = Path("/captures") / default_image_filename(
            "case/001",
            "cp:raw",
        )
        existing = {
            planned,
            Path("/captures/case_001__cp_raw_2.png"),
        }
        renamed = auto_rename_path(
            planned,
            path_exists=existing.__contains__,
        )
        self.assertEqual(Path("/captures/case_001__cp_raw_3.png"), renamed)
        self.assertEqual(
            Path("/captures/case_001__cp_raw_4.png"),
            auto_rename_path(
                planned,
                path_exists=existing.__contains__,
                reserved_paths={renamed},
            ),
        )


if __name__ == "__main__":
    unittest.main()
