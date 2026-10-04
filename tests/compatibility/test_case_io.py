import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from panelsolver.app.csv_writer import CSV_ENCODING
from panelsolver.domains.fmf import read_cases as read_fmf_cases
from panelsolver.domains.hypersonic import read_cases as read_newt_cases
from tests.current_case_fixtures import read_current_cases

_INPUTS = Path(__file__).parents[1] / "fixtures" / "phase1" / "inputs"
_GOLDEN = Path(__file__).parents[1] / "fixtures" / "phase1" / "golden"


def _write_case_table(frame: pd.DataFrame, path: Path) -> None:
    if path.suffix == ".csv":
        frame.to_csv(path, index=False)
        return
    if path.suffix == ".xlsx":
        frame.to_excel(path, index=False, engine="openpyxl")
        return
    if path.suffix == ".xlsm":
        xlsx = path.with_suffix(".xlsx")
        frame.to_excel(xlsx, index=False, engine="openpyxl")
        shutil.copyfile(xlsx, path)
        return
    raise AssertionError(f"Unsupported test case-table suffix: {path.suffix}")


class CaseReaderCompatibilityTests(unittest.TestCase):
    def test_readers_reject_removed_npz_field_regardless_of_flag_value(self) -> None:
        cases = (
            (read_fmf_cases, "fmfsolver_cases.csv", ".csv", 0),
            (read_newt_cases, "newtsolver_cases.csv", ".xlsx", 1),
        )
        for reader, filename, suffix, value in cases:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as td:
                frame = read_current_cases(reader, _INPUTS / filename).iloc[[0]].copy()
                frame["save_npz_on"] = value
                path = Path(td) / f"case{suffix}"
                _write_case_table(frame, path)
                with self.assertRaises(Exception) as caught:
                    reader(path)
                error = caught.exception
                self.assertEqual("InputValidationError", type(error).__name__)
                self.assertEqual(
                    ["save_npz_on"], [issue.field for issue in error.issues]
                )
                self.assertIn("has been removed", str(error))
                self.assertIn("Delete this field", str(error))
                self.assertIn("no longer writes NPZ files", str(error))

    def test_csv_reader_accepts_bomless_bom_and_japanese_utf8(self) -> None:
        products = (
            (read_fmf_cases, "fmfsolver_cases.csv"),
            (read_newt_cases, "newtsolver_cases.csv"),
        )
        for reader, filename in products:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as td:
                frame = read_current_cases(reader, _INPUTS / filename).iloc[[0]].copy()
                frame.loc[frame.index[0], "case_id"] = "日本語ケース"
                frame["user_note"] = "日本語メモ"
                path = Path(td) / filename
                for encoding in ("utf-8", CSV_ENCODING):
                    with self.subTest(encoding=encoding):
                        frame.to_csv(path, index=False, encoding=encoding)
                        actual = reader(path)
                        self.assertEqual("日本語ケース", actual.iloc[0]["case_id"])
                        self.assertEqual("日本語メモ", actual.iloc[0]["user_note"])

    def test_invalid_phase1_tables_preserve_structured_issue_contracts(self) -> None:
        for product, reader in (
            ("fmfsolver", read_fmf_cases),
            ("newtsolver", read_newt_cases),
        ):
            contract = json.loads((_GOLDEN / product / "contracts.json").read_text())
            for filename, expected in contract["invalid_inputs"].items():
                with self.subTest(product=product, filename=filename):
                    if filename == "fmf_beta_tan_90.csv":
                        # ADR 0017 promotes this historical invalid input.
                        actual = reader(_INPUTS / "invalid" / filename)
                        self.assertEqual(90, abs(actual.iloc[0]["alpha_deg"]))
                        continue
                    with self.assertRaises(Exception) as caught:
                        reader(_INPUTS / "invalid" / filename)
                    error = caught.exception
                    self.assertEqual("InputValidationError", type(error).__name__)
                    self.assertEqual(
                        [
                            (issue["row_number"], issue["case_id"], issue["field"])
                            for issue in expected["issues"]
                        ],
                        [
                            (issue.row_number, issue.case_id, issue.field)
                            for issue in error.issues
                        ],
                    )

    def test_csv_xlsx_and_xlsm_preserve_valid_rows(self) -> None:
        for reader, filename, case_id, major_values in (
            (
                read_fmf_cases,
                "fmfsolver_cases.csv",
                "001",
                {"S": 5.0, "Ti_K": 300.0, "Tw_K": 300.0},
            ),
            (
                read_newt_cases,
                "newtsolver_cases.csv",
                "001",
                {
                    "Mach": 6.0,
                    "gamma": 1.4,
                    "windward_eq": "newtonian",
                    "leeward_eq": "shield",
                },
            ),
        ):
            with tempfile.TemporaryDirectory() as temp_dir:
                temp = Path(temp_dir)
                geometry = temp / "geometry"
                geometry.mkdir()
                shutil.copyfile(_INPUTS / "stl" / "plate.stl", geometry / "plate.stl")
                source = read_current_cases(reader, _INPUTS / filename).iloc[[0]].copy()
                source.loc[source.index[0], "case_id"] = case_id
                source.loc[source.index[0], "stl_path"] = "geometry/plate.stl"
                source.loc[source.index[0], "out_dir"] = "outputs"
                paths = tuple(
                    temp / f"cases{suffix}" for suffix in (".csv", ".xlsx", ".xlsm")
                )
                for path in paths:
                    _write_case_table(source, path)
                csv_frame = reader(paths[0])
                for path in paths:
                    with self.subTest(filename=filename, suffix=path.suffix):
                        actual = reader(path)
                        self.assertEqual(1, len(actual))
                        self.assertEqual([case_id], actual["case_id"].tolist())
                        self.assertEqual(list(csv_frame.columns), list(actual.columns))
                        for name, expected in major_values.items():
                            self.assertEqual(expected, actual.iloc[0][name])
                        self.assertEqual(
                            (geometry / "plate.stl").resolve(),
                            Path(actual.iloc[0]["stl_path"]),
                        )
                        self.assertEqual(
                            (temp / "outputs").resolve(),
                            Path(actual.iloc[0]["out_dir"]),
                        )

    def test_legacy_xls_is_rejected_before_excel_read_with_migration_help(self) -> None:
        for reader, stem in (
            (read_fmf_cases, "fmfsolver_cases"),
            (read_newt_cases, "newtsolver_cases"),
        ):
            with tempfile.TemporaryDirectory() as temp_dir:
                uppercase = Path(temp_dir) / f"{stem}.XLS"
                shutil.copyfile(_INPUTS / f"{stem}.xls", uppercase)
                for path in (_INPUTS / f"{stem}.xls", uppercase):
                    with (
                        self.subTest(stem=stem, suffix=path.suffix),
                        patch("panelsolver.app.case_io.pd.read_excel") as read_excel,
                    ):
                        with self.assertRaises(ValueError) as caught:
                            reader(path)
                    read_excel.assert_not_called()
                    message = str(caught.exception)
                    self.assertIn("Legacy .xls input is no longer supported", message)
                    self.assertIn(".xlsx", message)
                    self.assertIn(".csv", message)

    def test_case_ids_use_one_portable_unicode_and_casefold_policy(self) -> None:
        products = (
            (read_fmf_cases, "fmfsolver_cases.csv"),
            (read_newt_cases, "newtsolver_cases.csv"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            for reader, filename in products:
                base = read_current_cases(reader, _INPUTS / filename).iloc[[0]].copy()
                path = temp / filename
                for accepted in ("日本語", "Straße-ケース"):
                    with self.subTest(filename=filename, accepted=accepted):
                        frame = base.copy()
                        frame.loc[frame.index[0], "case_id"] = accepted
                        frame.to_csv(path, index=False)
                        self.assertEqual(accepted, reader(path).iloc[0]["case_id"])
                for rejected in (
                    "",
                    ".",
                    "..",
                    "a/b",
                    "a\\b",
                    "a:name",
                    "a\nb",
                    "CON",
                    "con.txt",
                    "name.",
                    "name ",
                ):
                    with self.subTest(filename=filename, rejected=rejected):
                        frame = base.copy()
                        frame.loc[frame.index[0], "case_id"] = rejected
                        frame.to_csv(path, index=False)
                        with self.assertRaises(Exception) as caught:
                            reader(path)
                        self.assertEqual(
                            "InputValidationError", type(caught.exception).__name__
                        )
                        self.assertIn(
                            "case_id",
                            [issue.field for issue in caught.exception.issues],
                        )

                duplicates = pd.concat([base, base], ignore_index=True)
                duplicates.loc[0, "case_id"] = "Straße"
                duplicates.loc[1, "case_id"] = "STRASSE"
                duplicates.to_csv(path, index=False)
                with self.assertRaisesRegex(Exception, "Unicode casefold"):
                    reader(path)

                nfc_equivalent_duplicates = pd.concat([base, base], ignore_index=True)
                nfc_equivalent_duplicates.loc[0, "case_id"] = "é"
                nfc_equivalent_duplicates.loc[1, "case_id"] = (
                    "e\N{COMBINING ACUTE ACCENT}"
                )
                nfc_equivalent_duplicates.to_csv(path, index=False)
                with self.assertRaisesRegex(Exception, "Unicode casefold"):
                    reader(path)

                normalized_values = []
                for equivalent in ("é", "e\N{COMBINING ACUTE ACCENT}"):
                    frame = base.copy()
                    frame.loc[frame.index[0], "case_id"] = equivalent
                    frame.to_csv(path, index=False)
                    normalized_values.append(reader(path).iloc[0]["case_id"])
                self.assertEqual(["é", "é"], normalized_values)

                distinct = pd.concat([base, base], ignore_index=True)
                distinct.loc[0, "case_id"] = "é-a"
                distinct.loc[1, "case_id"] = "e\N{COMBINING ACUTE ACCENT}-b"
                distinct.to_csv(path, index=False)
                normalized = reader(path)["case_id"].tolist()
                self.assertEqual(["é-a", "é-b"], normalized)
                paths = {temp / f"{case_id}.vtp" for case_id in normalized}
                self.assertEqual(2, len(paths))

    def test_attitude_domains_are_common_and_mode_specific(self) -> None:
        products = (
            (read_fmf_cases, "fmfsolver_cases.csv"),
            (read_newt_cases, "newtsolver_cases.csv"),
        )
        rejected = (
            ("beta_tan", "beta_or_bank_deg", -90.001),
            ("beta_tan", "beta_or_bank_deg", 90.001),
            ("beta_sin", "beta_or_bank_deg", -90.001),
            ("beta_sin", "beta_or_bank_deg", 90.001),
        )
        accepted = (
            ("beta_tan", 89.999, -89.999),
            ("beta_tan", 90.0, 30.0),
            ("beta_tan", 100.0, 90.0),
            ("beta_sin", 90.0, 30.0),
            ("beta_sin", 460.0, 90.0),
            ("bank", 180.0, 1080.0),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            for reader, filename in products:
                base = read_current_cases(reader, _INPUTS / filename).iloc[[0]].copy()
                base[["alpha_deg", "beta_or_bank_deg"]] = base[
                    ["alpha_deg", "beta_or_bank_deg"]
                ].astype(float)
                path = temp / filename
                for mode, field, value in rejected:
                    with self.subTest(filename=filename, mode=mode, field=field):
                        frame = base.copy()
                        frame.loc[frame.index[0], "attitude_input"] = mode
                        frame.loc[frame.index[0], field] = value
                        frame.to_csv(path, index=False)
                        with self.assertRaises(Exception) as caught:
                            reader(path)
                        self.assertIn(
                            field, [issue.field for issue in caught.exception.issues]
                        )
                for mode, alpha, beta_or_bank in accepted:
                    with self.subTest(filename=filename, mode=mode, accepted=True):
                        frame = base.copy()
                        frame.loc[frame.index[0], "attitude_input"] = mode
                        frame.loc[frame.index[0], "alpha_deg"] = alpha
                        frame.loc[frame.index[0], "beta_or_bank_deg"] = beta_or_bank
                        frame.to_csv(path, index=False)
                        actual = reader(path).iloc[0]
                        self.assertEqual(mode, actual["attitude_input"])


if __name__ == "__main__":
    unittest.main()
