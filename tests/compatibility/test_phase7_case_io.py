import json
import shutil
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from fmfsolver._frontend import (
    _build_artifact_signatures as build_fmf_signatures,
)
from newtsolver._frontend import (
    _build_artifact_signatures as build_newt_signatures,
)
from panelsolver._compat.versions import (
    FMFSOLVER_COMPATIBILITY_VERSION,
    NEWTSOLVER_COMPATIBILITY_VERSION,
)
from panelsolver.app.csv_writer import CSV_ENCODING
from panelsolver.core import MeshValidationPolicy, execute_case
from panelsolver.domains import fmf as fmf_case_module
from panelsolver.domains import hypersonic as newt_case_module
from panelsolver.domains.fmf import adapt_row as adapt_fmf_row
from panelsolver.domains.fmf import read_cases as read_fmf_cases
from panelsolver.domains.hypersonic import adapt_row as adapt_newt_row
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


class ProductCaseReaderTests(unittest.TestCase):
    def test_removed_npz_field_is_absent_from_current_schemas_and_defaults(self) -> None:
        for module in (fmf_case_module, newt_case_module):
            with self.subTest(product=module.__name__):
                self.assertNotIn("save_npz_on", module.INPUT_COLUMN_ORDER)
                self.assertNotIn("save_npz_on", module.DEFAULTS)

    def test_csv_and_excel_reject_removed_npz_field_for_any_value(self) -> None:
        products = (
            (read_fmf_cases, "fmfsolver_cases.csv"),
            (read_newt_cases, "newtsolver_cases.csv"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for reader, filename in products:
                base = read_current_cases(reader, _INPUTS / filename).iloc[[0]].copy()
                for value in (0, 1):
                    for suffix in (".csv", ".xlsx", ".xlsm"):
                        with self.subTest(filename=filename, value=value, suffix=suffix):
                            frame = base.copy()
                            frame["save_npz_on"] = value
                            path = root / f"{Path(filename).stem}-{value}{suffix}"
                            _write_case_table(frame, path)
                            with self.assertRaises(Exception) as caught:
                                reader(path)
                            error = caught.exception
                            self.assertEqual("InputValidationError", type(error).__name__)
                            self.assertEqual(
                                ["save_npz_on"],
                                [issue.field for issue in error.issues],
                            )
                            self.assertIn("has been removed", str(error))
                            self.assertIn("Delete this field", str(error))
                            self.assertIn("no longer writes NPZ files", str(error))

    def test_other_unknown_columns_remain_preserved(self) -> None:
        for reader, filename in (
            (read_fmf_cases, "fmfsolver_cases.csv"),
            (read_newt_cases, "newtsolver_cases.csv"),
        ):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as td:
                frame = read_current_cases(reader, _INPUTS / filename).iloc[[0]].copy()
                frame["user_note"] = "preserved"
                path = Path(td) / filename
                frame.to_csv(path, index=False)
                actual = reader(path)
                self.assertEqual("preserved", actual.iloc[0]["user_note"])

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
                        with patch(
                            "panelsolver.app.case_io.pd.read_csv",
                            wraps=pd.read_csv,
                        ) as read_csv:
                            actual = reader(path)
                        self.assertEqual(
                            CSV_ENCODING,
                            read_csv.call_args.kwargs["encoding"],
                        )
                        self.assertEqual("日本語ケース", actual.iloc[0]["case_id"])
                        self.assertEqual("日本語メモ", actual.iloc[0]["user_note"])

    def test_valid_phase1_tables_preserve_rows_columns_defaults_and_paths(self) -> None:
        products = (
            ("fmfsolver", read_fmf_cases, "fmfsolver_cases.csv", 6),
            ("newtsolver", read_newt_cases, "newtsolver_cases.csv", 9),
        )
        for product, reader, filename, row_count in products:
            with self.subTest(product=product):
                frame = read_current_cases(reader, _INPUTS / filename)
                contract = json.loads(
                    (_GOLDEN / product / "contracts.json").read_text()
                )
                expected_columns = [
                    name
                    for name in contract["cli_run"]["result_csv_columns"]
                    if name != "save_npz_on"
                ][: len(frame.columns)]
                self.assertEqual(row_count, len(frame))
                self.assertEqual(expected_columns, list(frame.columns))
                self.assertNotIn("save_npz_on", frame.columns)
                self.assertTrue(frame["stl_path"].map(Path).map(Path.is_absolute).all())
                self.assertTrue(frame["out_dir"].map(Path).map(Path.is_absolute).all())

    def test_invalid_phase1_tables_preserve_structured_issue_contracts(self) -> None:
        for product, reader in (
            ("fmfsolver", read_fmf_cases),
            ("newtsolver", read_newt_cases),
        ):
            contract = json.loads(
                (_GOLDEN / product / "contracts.json").read_text()
            )
            for filename, expected in contract["invalid_inputs"].items():
                with self.subTest(product=product, filename=filename):
                    with self.assertRaises(Exception) as caught:
                        reader(_INPUTS / "invalid" / filename)
                    error = caught.exception
                    self.assertEqual("InputValidationError", type(error).__name__)
                    if filename == "fmf_beta_tan_90.csv":
                        self.assertEqual(["alpha_deg"], [issue.field for issue in error.issues])
                        continue
                    self.assertEqual(expected["message"], str(error))
                    self.assertEqual(
                        expected["issues"],
                        [asdict(issue) for issue in error.issues],
                    )

    def test_ooxml_excel_engine_dispatch_is_common(self) -> None:
        for reader, filename in (
            (read_fmf_cases, "fmfsolver_cases.csv"),
            (read_newt_cases, "newtsolver_cases.csv"),
        ):
            frame = read_current_cases(reader, _INPUTS / filename)
            for suffix in (".xlsx", ".xlsm"):
                with self.subTest(filename=filename, suffix=suffix), patch(
                    "panelsolver.app.case_io.pd.read_excel",
                    return_value=frame.copy(),
                ) as read_excel:
                    reader(f"cases{suffix}")
                    self.assertEqual(
                        "openpyxl", read_excel.call_args.kwargs["engine"]
                    )
                    self.assertEqual(
                        {"case_id": "string"}, read_excel.call_args.kwargs["dtype"]
                    )

    def test_csv_xlsx_and_xlsm_preserve_valid_rows(self) -> None:
        for reader, filename, case_id, major_values in (
            (
                read_fmf_cases,
                "fmfsolver_cases.csv",
                "fmf_supported_formats",
                {"S": 5.0, "Ti_K": 300.0, "Tw_K": 300.0},
            ),
            (
                read_newt_cases,
                "newtsolver_cases.csv",
                "newt_supported_formats",
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
                    temp / f"cases{suffix}"
                    for suffix in (".csv", ".xlsx", ".xlsm")
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
                    with self.subTest(stem=stem, suffix=path.suffix), patch(
                        "panelsolver.app.case_io.pd.read_excel"
                    ) as read_excel:
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
                            "case_id", [issue.field for issue in caught.exception.issues]
                        )

                duplicates = pd.concat([base, base], ignore_index=True)
                duplicates.loc[0, "case_id"] = "Straße"
                duplicates.loc[1, "case_id"] = "STRASSE"
                duplicates.to_csv(path, index=False)
                with self.assertRaisesRegex(Exception, "Unicode casefold"):
                    reader(path)

                canonical_duplicates = pd.concat([base, base], ignore_index=True)
                canonical_duplicates.loc[0, "case_id"] = "é"
                canonical_duplicates.loc[1, "case_id"] = "e\N{COMBINING ACUTE ACCENT}"
                canonical_duplicates.to_csv(path, index=False)
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
            ("beta_tan", "alpha_deg", -90.0),
            ("beta_tan", "alpha_deg", 90.0),
            ("beta_tan", "beta_or_bank_deg", -90.0),
            ("beta_tan", "beta_or_bank_deg", 90.0),
            ("beta_sin", "alpha_deg", -90.0),
            ("beta_sin", "alpha_deg", 90.0),
        )
        accepted = (
            ("beta_tan", 89.999, -89.999),
            ("beta_sin", 89.999, 90.0),
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


class ProductCaseAdapterTests(unittest.TestCase):
    def test_rows_bind_independent_models_mesh_policies_and_environment_prefixes(self) -> None:
        fmf_row = read_current_cases(
            read_fmf_cases, _INPUTS / "fmfsolver_cases.csv"
        ).iloc[0].to_dict()
        newt_row = read_current_cases(
            read_newt_cases, _INPUTS / "newtsolver_cases.csv"
        ).iloc[0].to_dict()
        fmf = adapt_fmf_row(fmf_row)
        newt = adapt_newt_row(newt_row)
        self.assertEqual("sentman", fmf.request.model_case.model_id)
        self.assertEqual(MeshValidationPolicy.STRICT, fmf.request.mesh_validation_policy)
        self.assertFalse(hasattr(fmf.request.shielding, "legacy_env_prefix"))
        self.assertEqual("hypersonic", newt.request.model_case.model_id)
        self.assertEqual(MeshValidationPolicy.STRICT, newt.request.mesh_validation_policy)
        self.assertFalse(hasattr(newt.request.shielding, "legacy_env_prefix"))
        self.assertEqual("1.3.8", FMFSOLVER_COMPATIBILITY_VERSION)
        self.assertEqual("1.0.3", NEWTSOLVER_COMPATIBILITY_VERSION)

    def test_prepared_primary_signature_is_exactly_the_execution_signature(self) -> None:
        cases = (
            (
                read_current_cases(
                    read_fmf_cases, _INPUTS / "fmfsolver_cases.csv"
                ).iloc[0].to_dict(),
                adapt_fmf_row,
                build_fmf_signatures,
            ),
            (
                read_current_cases(
                    read_newt_cases, _INPUTS / "newtsolver_cases.csv"
                ).iloc[0].to_dict(),
                adapt_newt_row,
                build_newt_signatures,
            ),
        )
        for row, adapter, signature_builder in cases:
            with self.subTest(case_id=row["case_id"]):
                candidates = signature_builder(row)
                result = execute_case(adapter(row).request)
                self.assertEqual(result.signature, candidates.primary)
                self.assertGreaterEqual(len(candidates.legacy_signatures), 1)

    def test_direct_and_default_normalized_legacy_candidates_stay_ordered(self) -> None:
        for frame, builder in (
            (
                read_current_cases(read_fmf_cases, _INPUTS / "fmfsolver_cases.csv"),
                build_fmf_signatures,
            ),
            (
                read_current_cases(read_newt_cases, _INPUTS / "newtsolver_cases.csv"),
                build_newt_signatures,
            ),
        ):
            row = frame.iloc[0].to_dict()
            row.pop("attitude_input")
            with self.subTest(case_id=row["case_id"]):
                candidates = builder(row)
                self.assertEqual(2, len(candidates.legacy_signatures))
                self.assertNotEqual(*candidates.legacy_signatures)

    def test_beta_sin_endpoint_does_not_escape_beta_tan_principal_domain(self) -> None:
        frame = read_current_cases(read_newt_cases, _INPUTS / "newtsolver_cases.csv")
        beta_sin = frame.loc[
            frame["case_id"] == "newt_beta_sin_boundary"
        ].iloc[0].to_dict()
        beta_tan = dict(beta_sin)
        beta_tan["attitude_input"] = "beta_tan"

        adapted_sin = adapt_newt_row(beta_sin)
        execute_case(adapted_sin.request)
        with self.assertRaisesRegex(ValueError, "strictly between -90 and 90"):
            adapt_newt_row(beta_tan)


if __name__ == "__main__":
    unittest.main()
