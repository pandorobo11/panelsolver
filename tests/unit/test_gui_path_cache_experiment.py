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
    _resolve_out_dirs,
    _validate_and_resolve_stl_paths,
)
from panelsolver.app.gui_input_profile import gui_input_path_mode
from panelsolver.domains.fmf import read_cases as read_fmf_cases
from tests.current_case_fixtures import read_current_cases

_INPUTS = Path(__file__).parents[1] / "fixtures" / "phase1" / "inputs"
_MODES = ("baseline", "stl_cache", "all_path_cache")


def _current_fmf_row() -> pd.DataFrame:
    with patch.dict(os.environ, {"PANELSOLVER_GUI_PATH_MODE": "baseline"}):
        return read_current_cases(
            read_fmf_cases,
            _INPUTS / "fmfsolver_cases.csv",
        ).iloc[[0]].copy()


class GuiPathCacheExperimentTests(unittest.TestCase):
    def test_path_mode_defaults_to_baseline_and_rejects_unknown_values(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual("baseline", gui_input_path_mode())
        with patch.dict(os.environ, {"PANELSOLVER_GUI_PATH_MODE": "   "}):
            self.assertEqual("baseline", gui_input_path_mode())
        with patch.dict(os.environ, {"PANELSOLVER_GUI_PATH_MODE": "unknown"}):
            with self.assertRaisesRegex(ValueError, "must be one of"):
                gui_input_path_mode()

    def test_duplicate_stl_calls_drop_only_in_cache_modes(self) -> None:
        source = pd.DataFrame(
            {
                "stl_path": (
                    "folder/../same.stl",
                    "same.stl",
                    "/absolute/other.stl",
                    "/absolute/other.stl",
                    "same.stl;/absolute/other.stl",
                )
            }
        )

        def run(mode: str) -> tuple[pd.DataFrame, int, int, list[tuple]]:
            frame = source.copy()
            issues: list[tuple] = []
            with (
                patch.object(Path, "exists", autospec=True, return_value=True) as exists,
                patch.object(
                    Path,
                    "resolve",
                    autospec=True,
                    side_effect=lambda path: Path("/resolved") / path.name,
                ) as resolve,
            ):
                _validate_and_resolve_stl_paths(
                    frame,
                    Path("/input/cases.csv"),
                    lambda *issue: issues.append(issue),
                    mode,
                )
            return frame, exists.call_count, resolve.call_count, issues

        baseline, baseline_exists, baseline_resolve, baseline_issues = run(
            "baseline"
        )
        stl_cache, cache_exists, cache_resolve, cache_issues = run("stl_cache")
        all_cache, all_exists, all_resolve, all_issues = run("all_path_cache")

        self.assertEqual(6, baseline_exists)
        self.assertEqual(6, baseline_resolve)
        self.assertEqual(2, cache_exists)
        self.assertEqual(2, cache_resolve)
        self.assertEqual(2, all_exists)
        self.assertEqual(2, all_resolve)
        self.assertEqual([], baseline_issues)
        self.assertEqual(baseline_issues, cache_issues)
        self.assertEqual(baseline_issues, all_issues)
        pd.testing.assert_frame_equal(baseline, stl_cache)
        pd.testing.assert_frame_equal(baseline, all_cache)

    def test_repeated_missing_stl_caches_not_found_but_keeps_each_issue(self) -> None:
        source = pd.DataFrame({"stl_path": ("missing.stl",) * 3})

        def run(mode: str) -> tuple[int, int, list[tuple]]:
            frame = source.copy()
            issues: list[tuple] = []
            with (
                patch.object(
                    Path,
                    "exists",
                    autospec=True,
                    return_value=False,
                ) as exists,
                patch.object(Path, "resolve", autospec=True) as resolve,
            ):
                _validate_and_resolve_stl_paths(
                    frame,
                    Path("/input/cases.csv"),
                    lambda *issue: issues.append(issue),
                    mode,
                )
            return exists.call_count, resolve.call_count, issues

        baseline_exists, baseline_resolve, baseline_issues = run("baseline")
        cache_exists, cache_resolve, cache_issues = run("stl_cache")
        all_exists, all_resolve, all_issues = run("all_path_cache")

        self.assertEqual((3, 0), (baseline_exists, baseline_resolve))
        self.assertEqual((1, 0), (cache_exists, cache_resolve))
        self.assertEqual((1, 0), (all_exists, all_resolve))
        self.assertEqual(3, len(baseline_issues))
        self.assertEqual(baseline_issues, cache_issues)
        self.assertEqual(baseline_issues, all_issues)

    def test_duplicate_out_dir_calls_drop_only_in_all_path_cache(self) -> None:
        source = pd.DataFrame(
            {"out_dir": ("outputs", "outputs", "other", "outputs", "other")}
        )

        def resolve(raw: str, _input_path: Path) -> Path:
            return Path("/resolved") / raw

        def run(mode: str) -> tuple[pd.DataFrame, int]:
            frame = source.copy()
            with patch(
                "panelsolver.app.case_io.resolve_input_relative_path",
                side_effect=resolve,
            ) as resolver:
                _resolve_out_dirs(frame, Path("/input/cases.csv"), mode)
            return frame, resolver.call_count

        baseline, baseline_calls = run("baseline")
        stl_cache, stl_calls = run("stl_cache")
        all_cache, all_calls = run("all_path_cache")
        self.assertEqual(5, baseline_calls)
        self.assertEqual(5, stl_calls)
        self.assertEqual(2, all_calls)
        pd.testing.assert_frame_equal(baseline, stl_cache)
        pd.testing.assert_frame_equal(baseline, all_cache)

    def test_valid_rows_are_identical_for_relative_absolute_multi_stl_and_out_dirs(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            geometry = root / "geometry"
            geometry.mkdir()
            relative_stl = geometry / "relative.stl"
            absolute_stl = root / "absolute.stl"
            for target in (relative_stl, absolute_stl):
                shutil.copyfile(_INPUTS / "stl" / "plate.stl", target)
            base = _current_fmf_row()
            frame = pd.concat([base] * 5, ignore_index=True)
            frame["case_id"] = [f"cache_case_{index}" for index in range(5)]
            frame["stl_path"] = (
                "geometry/relative.stl",
                "geometry/relative.stl",
                str(absolute_stl),
                f"geometry/relative.stl;{absolute_stl}",
                str(absolute_stl),
            )
            frame["out_dir"] = ("outputs", "outputs", "other", "outputs", "other")
            input_path = root / "cases.csv"
            frame.to_csv(input_path, index=False)

            actual = {}
            for mode in _MODES:
                with patch.dict(os.environ, {"PANELSOLVER_GUI_PATH_MODE": mode}):
                    actual[mode] = read_fmf_cases(input_path)

        pd.testing.assert_frame_equal(actual["baseline"], actual["stl_cache"])
        pd.testing.assert_frame_equal(actual["baseline"], actual["all_path_cache"])

    def test_repeated_missing_stl_keeps_identical_issue_rows_in_all_modes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = _current_fmf_row()
            frame = pd.concat([base] * 3, ignore_index=True)
            frame["case_id"] = [f"missing_{index}" for index in range(3)]
            frame["stl_path"] = "missing/repeated.stl"
            input_path = root / "missing.csv"
            frame.to_csv(input_path, index=False)

            actual = {}
            for mode in _MODES:
                with (
                    patch.dict(os.environ, {"PANELSOLVER_GUI_PATH_MODE": mode}),
                    self.assertRaises(InputValidationError) as caught,
                ):
                    read_fmf_cases(input_path)
                actual[mode] = [asdict(issue) for issue in caught.exception.issues]

        self.assertEqual(actual["baseline"], actual["stl_cache"])
        self.assertEqual(actual["baseline"], actual["all_path_cache"])
        self.assertEqual([2, 3, 4], [issue["row_number"] for issue in actual["baseline"]])


if __name__ == "__main__":
    unittest.main()
