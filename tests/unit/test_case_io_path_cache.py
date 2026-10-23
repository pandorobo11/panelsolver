from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from panelsolver.app.case_io import (
    InputValidationError,
    _validate_and_resolve_stl_paths,
)
from panelsolver.domains.fmf import read_cases as read_fmf_cases
from tests.current_case_fixtures import read_current_cases

_INPUTS = Path(__file__).parents[1] / "fixtures" / "phase1" / "inputs"


def _current_fmf_row() -> pd.DataFrame:
    return (
        read_current_cases(
            read_fmf_cases,
            _INPUTS / "fmfsolver_cases.csv",
        )
        .iloc[[0]]
        .copy()
    )


class CaseIoPathCacheTests(unittest.TestCase):
    def test_stl_cache_does_not_lexically_collapse_parent_components(self) -> None:
        frame = pd.DataFrame({"stl_path": ("same.stl", "linked/../same.stl")})
        issues: list[tuple] = []
        with patch.object(
            Path,
            "exists",
            autospec=True,
            return_value=False,
        ) as exists:
            _validate_and_resolve_stl_paths(
                frame,
                Path("input") / "cases.csv",
                lambda *issue: issues.append(issue),
            )
        self.assertEqual(2, exists.call_count)
        self.assertEqual(2, len(issues))

    def test_repeated_tilde_stl_expands_to_home_and_keeps_component_order(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            shutil.copyfile(_INPUTS / "stl" / "plate.stl", home / "same.stl")
            frame = pd.DataFrame({"stl_path": ("~/same.stl;~/same.stl",)})
            issues: list[tuple] = []
            with patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
                _validate_and_resolve_stl_paths(
                    frame,
                    Path("input") / "cases.csv",
                    lambda *issue: issues.append(issue),
                )
            expanded = str((home / "same.stl").resolve())
        self.assertEqual([], issues)
        self.assertEqual(f"{expanded};{expanded}", frame.iloc[0]["stl_path"])

    def test_repeated_missing_stl_keeps_issue_attribution_and_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = pd.concat([_current_fmf_row()] * 5, ignore_index=True)
            source["case_id"] = [f"missing_{index}" for index in range(5)]
            source["stl_path"] = "missing/repeated.stl"
            input_path = root / "missing.csv"
            source.to_csv(input_path, index=False)

            with (
                patch.object(
                    Path,
                    "exists",
                    autospec=True,
                    return_value=False,
                ) as exists,
                patch.object(Path, "resolve", autospec=True) as resolve,
                self.assertRaises(InputValidationError) as caught,
            ):
                read_fmf_cases(input_path)

        expected_message = (
            "STL file not found: 'missing/repeated.stl' "
            f"(checked relative to '{root}')."
        )
        expected_issues = [
            {
                "row_number": index + 2,
                "case_id": f"missing_{index}",
                "field": "stl_path",
                "message": expected_message,
            }
            for index in range(5)
        ]
        self.assertEqual(1, exists.call_count)
        resolve.assert_not_called()
        self.assertEqual(
            expected_issues,
            [asdict(issue) for issue in caught.exception.issues],
        )
        expected_lines = ["Invalid input table:"] + [
            f"- row {issue['row_number']}, case_id='{issue['case_id']}', "
            f"stl_path: {expected_message}"
            for issue in expected_issues
        ]
        self.assertEqual("\n".join(expected_lines), str(caught.exception))

    def test_supported_stl_forms_keep_normalized_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            geometry = root / "geometry"
            geometry.mkdir()
            relative_stl = geometry / "relative.stl"
            different_stl = geometry / "different.stl"
            absolute_stl = root / "absolute.stl"
            for target in (relative_stl, different_stl, absolute_stl):
                shutil.copyfile(_INPUTS / "stl" / "plate.stl", target)

            source = pd.concat([_current_fmf_row()] * 7, ignore_index=True)
            source["case_id"] = [f"paths_{index}" for index in range(7)]
            source["stl_path"] = (
                "geometry/relative.stl",
                "geometry/relative.stl",
                str(absolute_stl),
                str(absolute_stl),
                "geometry/different.stl",
                f"geometry/relative.stl;{absolute_stl}",
                "geometry/relative.stl;geometry/relative.stl",
            )
            input_path = root / "cases.csv"
            source.to_csv(input_path, index=False)

            actual = read_fmf_cases(input_path)
            relative = str(relative_stl.resolve())
            absolute = str(absolute_stl.resolve())
            expected_stl_paths = [
                relative,
                relative,
                absolute,
                absolute,
                str(different_stl.resolve()),
                f"{relative};{absolute}",
                f"{relative};{relative}",
            ]

        self.assertEqual(
            expected_stl_paths,
            actual["stl_path"].tolist(),
        )


if __name__ == "__main__":
    unittest.main()
