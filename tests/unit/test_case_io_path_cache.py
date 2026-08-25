from __future__ import annotations

import shutil
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from panelsolver.app.case_io import (
    InputValidationError,
    _resolve_out_dirs,
    _validate_and_resolve_stl_paths,
)
from panelsolver.app.path_resolution import resolve_input_relative_path
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
    def test_stl_filesystem_calls_scale_with_unique_candidate_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base_dir = Path(directory)
            same_absolute = str(base_dir / "same.stl")
            values = (
                ("same.stl",) * 8
                + (same_absolute,) * 2
                + ("other.stl",) * 5
                + (str(base_dir / "third.stl"),) * 3
                + ("same.stl;other.stl",) * 2
            )
            source = pd.DataFrame({"stl_path": values})

            def fake_resolve(path: Path) -> Path:
                return Path(f"{path}.resolved")

            def run() -> tuple[pd.DataFrame, list[tuple]]:
                frame = source.copy()
                issues: list[tuple] = []
                _validate_and_resolve_stl_paths(
                    frame,
                    base_dir / "cases.csv",
                    lambda *issue: issues.append(issue),
                )
                return frame, issues

            with (
                patch.object(
                    Path,
                    "exists",
                    autospec=True,
                    return_value=True,
                ) as exists,
                patch.object(
                    Path,
                    "resolve",
                    autospec=True,
                    side_effect=fake_resolve,
                ) as resolve,
            ):
                actual, issues = run()
                self.assertEqual(3, exists.call_count)
                self.assertEqual(3, resolve.call_count)
                second, second_issues = run()

            self.assertEqual(6, exists.call_count)
            self.assertEqual(6, resolve.call_count)
            self.assertEqual([], issues)
            self.assertEqual([], second_issues)
            pd.testing.assert_frame_equal(actual, second)
            expected_same = str(fake_resolve(base_dir / "same.stl"))
            expected_other = str(fake_resolve(base_dir / "other.stl"))
            expected_third = str(fake_resolve(base_dir / "third.stl"))
            self.assertEqual(expected_same, actual.iloc[0]["stl_path"])
            self.assertEqual(expected_same, actual.iloc[9]["stl_path"])
            self.assertEqual(expected_other, actual.iloc[10]["stl_path"])
            self.assertEqual(expected_third, actual.iloc[15]["stl_path"])
            self.assertEqual(
                f"{expected_same};{expected_other}",
                actual.iloc[18]["stl_path"],
            )

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

    def test_repeated_tilde_stl_keeps_expansion_and_component_order(self) -> None:
        frame = pd.DataFrame({"stl_path": ("~/same.stl;~/same.stl",)})
        issues: list[tuple] = []
        with (
            patch.object(
                Path,
                "exists",
                autospec=True,
                return_value=True,
            ) as exists,
            patch.object(
                Path,
                "resolve",
                autospec=True,
                side_effect=lambda path: path,
            ) as resolve,
        ):
            _validate_and_resolve_stl_paths(
                frame,
                Path("input") / "cases.csv",
                lambda *issue: issues.append(issue),
            )
        expanded = str(Path("~/same.stl").expanduser())
        self.assertEqual([], issues)
        self.assertEqual(1, exists.call_count)
        self.assertEqual(1, resolve.call_count)
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

    def test_out_dir_resolution_scales_with_unique_candidate_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            absolute = root / "absolute"
            values = ("outputs",) * 10 + ("other",) * 5 + (str(absolute),) * 5
            source = pd.DataFrame({"out_dir": values})

            with patch(
                "panelsolver.app.case_io.resolve_input_relative_path",
                wraps=resolve_input_relative_path,
            ) as resolver:
                actual = source.copy()
                _resolve_out_dirs(actual, root / "cases.csv")
                self.assertEqual(3, resolver.call_count)
                second = source.copy()
                _resolve_out_dirs(second, root / "cases.csv")

            self.assertEqual(6, resolver.call_count)
            pd.testing.assert_frame_equal(actual, second)
            expected = (
                [str((root / "outputs").resolve())] * 10
                + [str((root / "other").resolve())] * 5
                + [str(absolute.resolve())] * 5
            )
            self.assertEqual(expected, actual["out_dir"].tolist())

    def test_out_dir_cache_preserves_distinct_input_spelling(self) -> None:
        source = pd.DataFrame({"out_dir": ("outputs", "OUTPUTS")})

        def preserve_spelling(raw: str, _input_path: Path) -> Path:
            return Path("resolved") / raw

        with patch(
            "panelsolver.app.case_io.resolve_input_relative_path",
            side_effect=preserve_spelling,
        ) as resolver:
            _resolve_out_dirs(source, Path("input") / "cases.csv")

        self.assertEqual(2, resolver.call_count)
        self.assertEqual(
            [str(Path("resolved/outputs")), str(Path("resolved/OUTPUTS"))],
            source["out_dir"].tolist(),
        )

    def test_supported_stl_and_out_dir_forms_keep_normalized_values(self) -> None:
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
            absolute_out = root / "absolute-output"
            source["out_dir"] = (
                "outputs",
                "outputs",
                "other",
                str(absolute_out),
                "",
                "other",
                "outputs",
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
            expected_out_dirs = [
                str((root / "outputs").resolve()),
                str((root / "outputs").resolve()),
                str((root / "other").resolve()),
                str(absolute_out.resolve()),
                str((root / "outputs").resolve()),
                str((root / "other").resolve()),
                str((root / "outputs").resolve()),
            ]

        self.assertEqual(
            expected_stl_paths,
            actual["stl_path"].tolist(),
        )
        self.assertEqual(
            expected_out_dirs,
            actual["out_dir"].tolist(),
        )


if __name__ == "__main__":
    unittest.main()
