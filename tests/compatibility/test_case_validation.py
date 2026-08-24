from __future__ import annotations

import tempfile
import unittest
from collections.abc import Callable, Iterable
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from openpyxl import Workbook

from panelsolver.app.case_io import InputValidationError, normalize_optional_text
from panelsolver.domains.fmf import read_cases as read_fmf_cases
from panelsolver.domains.hypersonic import read_cases as read_newt_cases
from tests.current_case_fixtures import read_current_cases

_INPUTS = Path(__file__).parents[1] / "fixtures" / "phase1" / "inputs"
_BOUNDARY_VALUES = (
    ("zero", 0.0),
    ("negative", -1.0),
    ("nan", float("nan")),
    ("positive_infinity", float("inf")),
    ("negative_infinity", float("-inf")),
)
_FINITE_SIGNED_VALUE_NAMES = frozenset({"zero", "negative"})
_COMMON_POSITIVE_FIELDS = (
    "stl_scale_m_per_unit",
    "Aref_m2",
    "Lref_Cl_m",
    "Lref_Cm_m",
    "Lref_Cn_m",
)
_COMMON_SIGNED_FIELDS = (
    "alpha_deg",
    "beta_or_bank_deg",
    "ref_x_m",
    "ref_y_m",
    "ref_z_m",
)

type Reader = Callable[[str | Path], pd.DataFrame]


class CaseValidationMatrixTests(unittest.TestCase):
    def _write_openpyxl_workbook(
        self,
        frame: pd.DataFrame,
        path: Path,
        overrides: dict[str, object],
    ) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(list(frame.columns))
        for row_index, row in enumerate(frame.itertuples(index=False, name=None)):
            values = [value.item() if hasattr(value, "item") else value for value in row]
            if row_index == 0:
                for field, value in overrides.items():
                    values[frame.columns.get_loc(field)] = value
            sheet.append(values)
        workbook.save(path)
        workbook.close()

    def _assert_boundary(
        self,
        *,
        reader: Reader,
        base: pd.DataFrame,
        path: Path,
        field: str,
        value: float,
        accepted: bool,
        attributed_fields: Iterable[str],
    ) -> None:
        frame = base.copy()
        frame[field] = frame[field].astype(object)
        frame.at[frame.index[0], field] = value
        frame.to_csv(path, index=False)
        if accepted:
            actual = reader(path)
            self.assertEqual(1, len(actual))
            self.assertEqual(value, actual.iloc[0][field])
            return

        with self.assertRaises(InputValidationError) as caught:
            reader(path)
        observed = {issue.field for issue in caught.exception.issues}
        self.assertTrue(
            observed.intersection(attributed_fields),
            f"{field} rejection was attributed only to {sorted(observed)!r}",
        )

    def test_optional_text_normalization_distinguishes_missing_from_non_text(
        self,
    ) -> None:
        for value in (None, pd.NA, float("nan"), np.float64("nan"), "", "   "):
            with self.subTest(value=repr(value)):
                self.assertEqual(
                    "fallback",
                    normalize_optional_text(
                        value,
                        field="selector",
                        default="fallback",
                    ),
                )
        self.assertEqual(
            "BETA_TAN",
            normalize_optional_text(
                "  BETA_TAN  ",
                field="selector",
                default="fallback",
            ),
        )
        for value in (False, True, np.bool_(False), 0, 1, 1.5, [], ["beta_tan"]):
            with self.subTest(value=repr(value)), self.assertRaisesRegex(
                TypeError, "selector"
            ):
                normalize_optional_text(
                    value,
                    field="selector",
                    default="fallback",
                )

    def test_common_numeric_fields_share_accept_reject_and_attribution(self) -> None:
        products = (
            ("fmfsolver", read_fmf_cases, "fmfsolver_cases.csv"),
            ("newtsolver", read_newt_cases, "newtsolver_cases.csv"),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for product, reader, filename in products:
                base = read_current_cases(reader, _INPUTS / filename).iloc[[0]].copy()
                path = root / filename
                for field in _COMMON_POSITIVE_FIELDS:
                    for value_name, value in _BOUNDARY_VALUES:
                        with self.subTest(
                            product=product,
                            field=field,
                            value=value_name,
                            accepted=False,
                        ):
                            self._assert_boundary(
                                reader=reader,
                                base=base,
                                path=path,
                                field=field,
                                value=value,
                                accepted=False,
                                attributed_fields=(field,),
                            )
                for field in _COMMON_SIGNED_FIELDS:
                    for value_name, value in _BOUNDARY_VALUES:
                        accepted = value_name in _FINITE_SIGNED_VALUE_NAMES
                        with self.subTest(
                            product=product,
                            field=field,
                            value=value_name,
                            accepted=accepted,
                        ):
                            self._assert_boundary(
                                reader=reader,
                                base=base,
                                path=path,
                                field=field,
                                value=value,
                                accepted=accepted,
                                attributed_fields=(field,),
                            )

    def test_fmf_model_fields_keep_mode_semantics_and_field_attribution(self) -> None:
        fmf_cases = read_current_cases(
            read_fmf_cases, _INPUTS / "fmfsolver_cases.csv"
        )
        mode_a = fmf_cases.iloc[[0]].copy()
        mode_b = fmf_cases.iloc[[1]].copy()
        matrices = (
            ("S", mode_a, frozenset({"S", "S,Ti_K"}), frozenset()),
            ("Ti_K", mode_a, frozenset({"Ti_K", "S,Ti_K"}), frozenset()),
            (
                "Mach",
                mode_b,
                frozenset({"Mach", "Mach,Altitude_km"}),
                frozenset(),
            ),
            ("Tw_K", mode_a, frozenset({"Tw_K"}), frozenset()),
            (
                "Altitude_km",
                mode_b,
                frozenset({"Altitude_km", "Mach,Altitude_km"}),
                frozenset({"zero"}),
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "fmf-boundary.csv"
            for field, base, attributed_fields, accepted_names in matrices:
                for value_name, value in _BOUNDARY_VALUES:
                    accepted = value_name in accepted_names
                    with self.subTest(
                        field=field,
                        value=value_name,
                        accepted=accepted,
                    ):
                        self._assert_boundary(
                            reader=read_fmf_cases,
                            base=base,
                            path=path,
                            field=field,
                            value=value,
                            accepted=accepted,
                            attributed_fields=attributed_fields,
                        )

    def test_newtsolver_model_fields_reject_unsafe_boundaries(self) -> None:
        base = read_current_cases(
            read_newt_cases, _INPUTS / "newtsolver_cases.csv"
        ).iloc[[0]].copy()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "newtsolver-boundary.csv"
            for field in ("Mach", "gamma"):
                for value_name, value in _BOUNDARY_VALUES:
                    with self.subTest(field=field, value=value_name, accepted=False):
                        self._assert_boundary(
                            reader=read_newt_cases,
                            base=base,
                            path=path,
                            field=field,
                            value=value,
                            accepted=False,
                            attributed_fields=(field,),
                        )

    def test_openpyxl_boolean_cells_are_flags_not_physical_numbers(self) -> None:
        products = (
            (
                "fmfsolver",
                read_fmf_cases,
                "fmfsolver_cases.csv",
                ("Aref_m2", "ref_x_m", "S", "Mach", "Ti_K", "Tw_K"),
            ),
            (
                "newtsolver",
                read_newt_cases,
                "newtsolver_cases.csv",
                ("Aref_m2", "ref_x_m", "Mach", "gamma"),
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for product, reader, filename, numeric_fields in products:
                source = read_current_cases(reader, _INPUTS / filename)
                for field in numeric_fields:
                    row_index = 1 if product == "fmfsolver" and field == "Mach" else 0
                    base = source.iloc[[row_index]].copy()
                    for value in (True, False):
                        with self.subTest(product=product, field=field, value=value):
                            path = root / f"{product}-{field}-{value}.xlsx"
                            self._write_openpyxl_workbook(base, path, {field: value})
                            with self.assertRaises(InputValidationError) as caught:
                                reader(path)
                            self.assertIn(
                                field,
                                {issue.field for issue in caught.exception.issues},
                            )

                base = source.iloc[[0]].copy()
                flags = {
                    "shielding_on": True,
                    "save_vtp_on": False,
                }
                path = root / f"{product}-flags.xlsx"
                self._write_openpyxl_workbook(base, path, flags)
                actual = reader(path).iloc[0]
                self.assertEqual(1, actual["shielding_on"])
                self.assertEqual(0, actual["save_vtp_on"])

                for text in ("true", "false"):
                    with self.subTest(product=product, text=text):
                        path = root / f"{product}-{text}.xlsx"
                        self._write_openpyxl_workbook(base, path, {"Aref_m2": text})
                        with self.assertRaises(InputValidationError) as caught:
                            reader(path)
                        self.assertIn(
                            "Aref_m2",
                            {issue.field for issue in caught.exception.issues},
                        )

    def test_openpyxl_selector_cells_reject_non_text_scalars(self) -> None:
        products = (
            (
                "fmfsolver",
                read_fmf_cases,
                "fmfsolver_cases.csv",
                ("attitude_input",),
            ),
            (
                "newtsolver",
                read_newt_cases,
                "newtsolver_cases.csv",
                ("attitude_input", "windward_eq", "leeward_eq"),
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for product, reader, filename, fields in products:
                base = read_current_cases(reader, _INPUTS / filename).iloc[[0]].copy()
                for field in fields:
                    for value in (False, True, 0, 1):
                        with self.subTest(
                            product=product,
                            field=field,
                            value=value,
                        ):
                            path = root / f"{product}-{field}-{value!s}.xlsx"
                            self._write_openpyxl_workbook(base, path, {field: value})
                            with self.assertRaises(InputValidationError) as caught:
                                reader(path)
                            self.assertIn(
                                field,
                                {issue.field for issue in caught.exception.issues},
                            )

    def test_openpyxl_missing_blank_and_valid_selectors_keep_contracts(self) -> None:
        products = (
            (
                "fmfsolver",
                read_fmf_cases,
                "fmfsolver_cases.csv",
                {"attitude_input": "beta_tan"},
            ),
            (
                "newtsolver",
                read_newt_cases,
                "newtsolver_cases.csv",
                {
                    "attitude_input": "beta_tan",
                    "windward_eq": "newtonian",
                    "leeward_eq": "shield",
                },
            ),
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for product, reader, filename, defaults in products:
                source = read_current_cases(reader, _INPUTS / filename)
                base = source.iloc[[0]].copy()
                for field, default in defaults.items():
                    for value_name, value in (("missing", None), ("blank", "   ")):
                        with self.subTest(
                            product=product,
                            field=field,
                            value=value_name,
                        ):
                            path = root / f"{product}-{field}-{value_name}.xlsx"
                            self._write_openpyxl_workbook(base, path, {field: value})
                            actual = reader(path)
                            self.assertEqual(default, actual.iloc[0][field])
                            self.assertEqual(list(source.columns), list(actual.columns))

                for mode in ("beta_tan", "beta_sin", "bank"):
                    with self.subTest(product=product, attitude_input=mode):
                        path = root / f"{product}-attitude-{mode}.xlsx"
                        self._write_openpyxl_workbook(
                            base,
                            path,
                            {"attitude_input": f"  {mode.upper()}  "},
                        )
                        self.assertEqual(mode, reader(path).iloc[0]["attitude_input"])

            newt_source = read_current_cases(
                read_newt_cases, _INPUTS / "newtsolver_cases.csv"
            )
            newt_base = newt_source.iloc[[0]].copy()
            for field, values in (
                (
                    "windward_eq",
                    (
                        "newtonian",
                        "modified_newtonian",
                        "tangent_wedge",
                        "tangent_cone",
                    ),
                ),
                ("leeward_eq", ("shield", "prandtl_meyer")),
            ):
                for value in values:
                    with self.subTest(field=field, value=value):
                        path = root / f"newtsolver-{field}-{value}.xlsx"
                        self._write_openpyxl_workbook(
                            newt_base,
                            path,
                            {field: f"  {value.upper()}  "},
                        )
                        self.assertEqual(value, read_newt_cases(path).iloc[0][field])

            multicomponent = newt_source.loc[
                newt_source["case_id"] == "newt_bank_multicomponent"
            ].iloc[[0]]
            path = root / "newtsolver-multicomponent.xlsx"
            self._write_openpyxl_workbook(multicomponent, path, {})
            actual = read_newt_cases(path).iloc[0]
            self.assertEqual("tangent_cone;newtonian", actual["windward_eq"])
            self.assertEqual("prandtl_meyer;shield", actual["leeward_eq"])

    def test_numpy_booleans_are_rejected_before_numeric_coercion(self) -> None:
        for reader, filename in (
            (read_fmf_cases, "fmfsolver_cases.csv"),
            (read_newt_cases, "newtsolver_cases.csv"),
        ):
            frame = read_current_cases(reader, _INPUTS / filename).iloc[[0]].copy()
            frame["Aref_m2"] = frame["Aref_m2"].astype(object)
            frame.at[frame.index[0], "Aref_m2"] = np.bool_(True)
            with patch("panelsolver.app.case_io.pd.read_excel", return_value=frame):
                with self.assertRaises(InputValidationError) as caught:
                    reader("cases.xlsx")
            self.assertIn(
                "Aref_m2", {issue.field for issue in caught.exception.issues}
            )


if __name__ == "__main__":
    unittest.main()
