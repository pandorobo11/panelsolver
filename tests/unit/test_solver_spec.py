import unittest
from pathlib import Path

from panelsolver.app import (
    CaseColumnKind,
    CaseColumnPresentation,
    CaseColumnWidthRole,
    GuiRunRequest,
    GuiRunResult,
    SolverGuiAdapters,
    SolverSpec,
)
from panelsolver.domains.fmf import format_case as format_fmf_case
from panelsolver.domains.fmf import gui_spec as fmf_solver_spec
from panelsolver.domains.hypersonic import format_case as format_newt_case
from panelsolver.domains.hypersonic import gui_spec as newt_solver_spec


def _format(row):
    return str(row.get("case_id", ""))


def _valid_spec(**changes) -> SolverSpec:
    values = {
        "product_id": "synthetic",
        "model_id": "model",
        "window_title": "Synthetic GUI",
        "domain_name": "Synthetic",
        "case_columns": ("case_id", "value"),
        "case_column_presentations": (
            CaseColumnPresentation(
                "case_id",
                "Case ID",
                CaseColumnKind.TEXT,
                CaseColumnWidthRole.IDENTIFIER,
            ),
            CaseColumnPresentation(
                "value",
                "Value",
                CaseColumnKind.NUMERIC,
                CaseColumnWidthRole.COMPACT_NUMERIC,
            ),
        ),
        "preferred_scalars": ("model_scalar", "area_m2"),
        "scalar_labels": {
            "model_scalar": "Model scalar",
            "area_m2": "Area [m^2]",
        },
        "format_case": _format,
    }
    values.update(changes)
    return SolverSpec(**values)


class SolverSpecTests(unittest.TestCase):
    def test_gui_run_contract_validates_rows_workers_paths_and_callbacks(self) -> None:
        request = GuiRunRequest(
            rows=({"case_id": "one"},),
            workers=2,
            checkpoint_every_cases=2000,
            output_path="results.csv",
            log=lambda _message: None,
            progress=lambda _done, _total: None,
            cancel_requested=lambda: False,
        )
        self.assertEqual(Path("results.csv"), request.output_path)
        self.assertEqual("one", request.rows[0]["case_id"])
        with self.assertRaises(ValueError):
            GuiRunRequest((), 1, 2000, Path("out.csv"), print, print, lambda: False)
        with self.assertRaises(ValueError):
            GuiRunRequest(
                request.rows, 0, 2000, Path("out.csv"), print, print, lambda: False
            )
        with self.assertRaises(TypeError):
            GuiRunRequest(
                request.rows, True, 2000, Path("out.csv"), print, print, lambda: False
            )
        with self.assertRaises(ValueError):
            GuiRunRequest(
                request.rows, 1, -1, Path("out.csv"), print, print, lambda: False
            )
        result = GuiRunResult("one.vtp", request.rows[0])
        self.assertEqual(Path("one.vtp"), result.first_vtp_path)
        with self.assertRaises(TypeError):
            GuiRunResult(first_case_row=object())

    def test_validates_identity_names_and_callbacks(self) -> None:
        for field in ("product_id", "model_id", "window_title", "domain_name"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                _valid_spec(**{field: " "})
        with self.assertRaises(ValueError):
            _valid_spec(case_columns=("value", "case_id"))
        with self.assertRaises(ValueError):
            _valid_spec(case_columns=("case_id", "case_id"))
        with self.assertRaises(TypeError):
            _valid_spec(case_column_presentations=("case_id", "value"))
        with self.assertRaises(ValueError):
            _valid_spec(
                case_column_presentations=(
                    CaseColumnPresentation(
                        "case_id",
                        "Case ID",
                        CaseColumnKind.TEXT,
                        CaseColumnWidthRole.IDENTIFIER,
                    ),
                    CaseColumnPresentation(
                        "case_id",
                        "Duplicate",
                        CaseColumnKind.TEXT,
                        CaseColumnWidthRole.IDENTIFIER,
                    ),
                )
            )
        with self.assertRaises(ValueError):
            _valid_spec(
                case_column_presentations=(
                    CaseColumnPresentation(
                        "case_id",
                        "Case ID",
                        CaseColumnKind.TEXT,
                        CaseColumnWidthRole.IDENTIFIER,
                    ),
                    CaseColumnPresentation(
                        "other",
                        "Other",
                        CaseColumnKind.TEXT,
                        CaseColumnWidthRole.FALLBACK,
                    ),
                )
            )
        with self.assertRaises(ValueError):
            _valid_spec(preferred_scalars=("model_scalar", "model_scalar"))
        with self.assertRaises(TypeError):
            _valid_spec(scalar_labels=())
        with self.assertRaises(ValueError):
            _valid_spec(scalar_labels={"model_scalar": "Same", "area_m2": "Same"})
        with self.assertRaises(ValueError):
            _valid_spec(scalar_labels={"model_scalar": "Model scalar"})
        with self.assertRaises(TypeError):
            _valid_spec(format_case=None)
        with self.assertRaises(TypeError):
            _valid_spec(adapters=object())

        with self.assertRaises(ValueError):
            CaseColumnPresentation(
                " ",
                "Label",
                CaseColumnKind.TEXT,
                CaseColumnWidthRole.IDENTIFIER,
            )
        with self.assertRaises(ValueError):
            CaseColumnPresentation(
                "name",
                " ",
                CaseColumnKind.TEXT,
                CaseColumnWidthRole.IDENTIFIER,
            )
        with self.assertRaises(TypeError):
            CaseColumnPresentation(
                "name",
                "Label",
                "text",  # type: ignore[arg-type]
                CaseColumnWidthRole.IDENTIFIER,
            )
        with self.assertRaises(TypeError):
            CaseColumnPresentation(
                "name",
                "Label",
                CaseColumnKind.TEXT,
                "identifier",  # type: ignore[arg-type]
            )

        labels = {"model_scalar": "Model scalar", "area_m2": "Area [m^2]"}
        spec = _valid_spec(scalar_labels=labels)
        labels["model_scalar"] = "Changed"
        self.assertEqual("Model scalar", spec.scalar_labels["model_scalar"])
        with self.assertRaises(TypeError):
            spec.scalar_labels["model_scalar"] = "Changed"
        with self.assertRaises(AttributeError):
            spec.case_column_presentations[0].label = "Changed"
        with self.assertRaises(AttributeError):
            spec.case_column_presentations[0].width_role = CaseColumnWidthRole.PATH

    def test_adapter_bundle_requires_every_member_to_be_callable(self) -> None:
        adapters = SolverGuiAdapters(
            read_cases=lambda _path: (),
            build_case_signature=lambda _row: (),
            run_cases=lambda _request: None,
            validate_output_path=lambda out, _input, _rows: Path(out),
            resolve_velocity_hat_stl=lambda _row: (1.0, 0.0, 0.0),
        )
        self.assertIs(adapters, _valid_spec(adapters=adapters).adapters)
        with self.assertRaises(TypeError):
            SolverGuiAdapters(
                read_cases=None,
                build_case_signature=lambda _row: (),
                run_cases=lambda _request: None,
                validate_output_path=lambda out, _input, _rows: Path(out),
                resolve_velocity_hat_stl=lambda _row: (1.0, 0.0, 0.0),
            )

    def test_product_specs_retain_titles_models_and_schemas(self) -> None:
        fmf = fmf_solver_spec()
        newt = newt_solver_spec()
        self.assertEqual("Panel Solver — FMF", fmf.window_title)
        self.assertEqual("sentman", fmf.model_id)
        self.assertEqual("FMF", fmf.domain_name)
        self.assertIn("S", fmf.case_columns)
        self.assertNotIn("gamma", fmf.case_columns)
        self.assertEqual("Panel Solver — Hypersonic", newt.window_title)
        self.assertEqual("hypersonic", newt.model_id)
        self.assertEqual("Hypersonic", newt.domain_name)
        self.assertIn("gamma", newt.case_columns)
        self.assertNotIn("S", newt.case_columns)
        self.assertEqual(
            fmf.case_columns, tuple(p.name for p in fmf.case_column_presentations)
        )
        self.assertEqual(
            newt.case_columns, tuple(p.name for p in newt.case_column_presentations)
        )
        fmf_presentations = {p.name: p for p in fmf.case_column_presentations}
        newt_presentations = {p.name: p for p in newt.case_column_presentations}
        self.assertEqual("Ti [K]", fmf_presentations["Ti_K"].label)
        self.assertEqual("Altitude [km]", fmf_presentations["Altitude_km"].label)
        self.assertIs(CaseColumnKind.NUMERIC, fmf_presentations["Mach"].kind)
        self.assertEqual("Windward equation", newt_presentations["windward_eq"].label)
        self.assertEqual("Gamma", newt_presentations["gamma"].label)
        self.assertIs(CaseColumnKind.NUMERIC, newt_presentations["Aref_m2"].kind)
        self.assertEqual(
            {
                "case_id": CaseColumnWidthRole.IDENTIFIER,
                "stl_path": CaseColumnWidthRole.PATH,
                "stl_scale_m_per_unit": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "S": CaseColumnWidthRole.COMPACT_NUMERIC,
                "Ti_K": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "Mach": CaseColumnWidthRole.COMPACT_NUMERIC,
                "Altitude_km": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "Tw_K": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "alpha_deg": CaseColumnWidthRole.COMPACT_NUMERIC,
                "beta_or_bank_deg": CaseColumnWidthRole.COMPACT_NUMERIC,
                "attitude_input": CaseColumnWidthRole.ENUM_TEXT,
                "ref_x_m": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "ref_y_m": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "ref_z_m": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "Aref_m2": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "Lref_Cl_m": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "Lref_Cm_m": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "Lref_Cn_m": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "shielding_on": CaseColumnWidthRole.FLAG,
                "ray_backend": CaseColumnWidthRole.ENUM_TEXT,
                "out_dir": CaseColumnWidthRole.PATH,
                "save_vtp_on": CaseColumnWidthRole.FLAG,
            },
            {name: value.width_role for name, value in fmf_presentations.items()},
        )
        self.assertEqual(
            {
                "case_id": CaseColumnWidthRole.IDENTIFIER,
                "stl_path": CaseColumnWidthRole.PATH,
                "stl_scale_m_per_unit": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "Mach": CaseColumnWidthRole.COMPACT_NUMERIC,
                "gamma": CaseColumnWidthRole.COMPACT_NUMERIC,
                "windward_eq": CaseColumnWidthRole.MODEL_TEXT,
                "leeward_eq": CaseColumnWidthRole.MODEL_TEXT,
                "alpha_deg": CaseColumnWidthRole.COMPACT_NUMERIC,
                "beta_or_bank_deg": CaseColumnWidthRole.COMPACT_NUMERIC,
                "attitude_input": CaseColumnWidthRole.ENUM_TEXT,
                "ref_x_m": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "ref_y_m": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "ref_z_m": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "Aref_m2": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "Lref_Cl_m": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "Lref_Cm_m": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "Lref_Cn_m": CaseColumnWidthRole.ENGINEERING_NUMERIC,
                "shielding_on": CaseColumnWidthRole.FLAG,
                "ray_backend": CaseColumnWidthRole.ENUM_TEXT,
                "out_dir": CaseColumnWidthRole.PATH,
                "save_vtp_on": CaseColumnWidthRole.FLAG,
            },
            {name: value.width_role for name, value in newt_presentations.items()},
        )
        self.assertEqual(
            (
                "normal_traction_coeff",
                "tangential_traction_coeff",
                "shielded",
                "theta_deg",
                "area_m2",
                "center_x_stl_m",
                "center_y_stl_m",
                "center_z_stl_m",
                "stl_index",
            ),
            fmf.preferred_scalars,
        )
        self.assertEqual(
            (
                "cp",
                "shielded",
                "theta_deg",
                "area_m2",
                "center_x_stl_m",
                "center_y_stl_m",
                "center_z_stl_m",
                "stl_index",
            ),
            newt.preferred_scalars,
        )
        self.assertEqual(
            "Normal traction coeff.", fmf.scalar_labels["normal_traction_coeff"]
        )
        self.assertEqual(
            "Tangential traction coeff.",
            fmf.scalar_labels["tangential_traction_coeff"],
        )
        self.assertEqual("Cp", newt.scalar_labels["cp"])
        expected_common = {
            "shielded": "Shielded",
            "theta_deg": "Theta [deg]",
            "area_m2": "Area [m^2]",
            "center_x_stl_m": "Center X [m]",
            "center_y_stl_m": "Center Y [m]",
            "center_z_stl_m": "Center Z [m]",
            "stl_index": "STL index",
        }
        for name, label in expected_common.items():
            self.assertEqual(label, fmf.scalar_labels[name])
            self.assertEqual(label, newt.scalar_labels[name])

    def test_product_case_formatting_remains_independent(self) -> None:
        self.assertEqual(
            "Case  f\nMode  A  ·  S  5.0  ·  Ti [K]  300.0  ·  Tw [K]  400.0\n"
            "Alpha_t [deg]  1.0  ·  Beta_s [deg]  2.0\nShielding  1  ·  Ray backend  rtree",
            format_fmf_case(
                {
                    "case_id": "f",
                    "S": 5.0,
                    "Ti_K": 300.0,
                    "Tw_K": 400.0,
                    "alpha_deg": 1.0,
                    "beta_or_bank_deg": 2.0,
                    "attitude_input": "beta_sin",
                    "shielding_on": 1,
                    "ray_backend": "rtree",
                }
            ),
        )
        self.assertEqual(
            "Case  n\nMach  6.0  ·  Gamma  1.4\n"
            "Windward  tangent_cone  ·  Leeward  shield\n"
            "Incidence [deg]  3.0  ·  Bank [deg]  4.0\n"
            "Shielding  0  ·  Ray backend  auto",
            format_newt_case(
                {
                    "case_id": "n",
                    "Mach": 6.0,
                    "gamma": 1.4,
                    "windward_eq": "tangent_cone",
                    "leeward_eq": "shield",
                    "alpha_deg": 3.0,
                    "beta_or_bank_deg": 4.0,
                    "attitude_input": "bank",
                    "shielding_on": 0,
                    "ray_backend": "auto",
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()
