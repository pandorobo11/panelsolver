import unittest

from panelsolver.domains.fmf import format_case as format_fmf_case
from panelsolver.domains.fmf import gui_spec as fmf_solver_spec
from panelsolver.domains.hypersonic import format_case as format_newt_case
from panelsolver.domains.hypersonic import gui_spec as newt_solver_spec


class SolverSpecTests(unittest.TestCase):
    def test_domain_specs_expose_model_inputs_and_load_scalars(self) -> None:
        fmf = fmf_solver_spec()
        hypersonic = newt_solver_spec()
        self.assertTrue({"S", "Ti_K", "Tw_K"}.issubset(fmf.case_columns))
        self.assertNotIn("gamma", fmf.case_columns)
        self.assertTrue(
            {"Mach", "gamma", "windward_eq", "leeward_eq"}.issubset(
                hypersonic.case_columns
            )
        )
        self.assertNotIn("S", hypersonic.case_columns)
        self.assertTrue(
            {"normal_traction_coeff", "tangential_traction_coeff"}.issubset(
                fmf.preferred_scalars
            )
        )
        self.assertIn("cp", hypersonic.preferred_scalars)

    def test_attitude_info_shows_original_inputs_for_both_domains(self) -> None:
        for formatter in (format_fmf_case, format_newt_case):
            for mode, first, second in (
                ("beta_sin", "Alpha", "Beta_s"),
                ("beta_tan", "Alpha", "Beta_t"),
                ("bank", "Incidence", "Bank"),
            ):
                with self.subTest(domain=formatter.__module__, mode=mode):
                    formatted = " ".join(
                        formatter(
                            {
                                "alpha_deg": 460.0,
                                "beta_or_bank_deg": 30.0,
                                "attitude_input": mode,
                            }
                        ).split()
                    )
                    self.assertIn(f"{first} [deg] 460.0", formatted)
                    self.assertIn(f"{second} [deg] 30.0", formatted)

    def test_case_information_includes_domain_values_and_units(self) -> None:
        cases = (
            (
                format_fmf_case,
                {
                    "case_id": "f",
                    "S": 5.0,
                    "Ti_K": 300.0,
                    "Tw_K": 400.0,
                    "shielding_on": 1,
                    "ray_backend": "rtree",
                },
                (
                    "Case f",
                    "Mode A",
                    "S 5.0",
                    "Ti [K] 300.0",
                    "Tw [K] 400.0",
                    "Shielding 1",
                    "Ray backend rtree",
                ),
            ),
            (
                format_newt_case,
                {
                    "case_id": "n",
                    "Mach": 6.0,
                    "gamma": 1.4,
                    "windward_eq": "tangent_cone",
                    "leeward_eq": "shield",
                    "shielding_on": 0,
                    "ray_backend": "auto",
                },
                (
                    "Case n",
                    "Mach 6.0",
                    "Gamma 1.4",
                    "Windward tangent_cone",
                    "Leeward shield",
                    "Shielding 0",
                    "Ray backend auto",
                ),
            ),
        )
        for formatter, row, expected_fields in cases:
            with self.subTest(domain=formatter.__module__):
                formatted = " ".join(formatter(row).split())
                for field in expected_fields:
                    self.assertIn(field, formatted)


if __name__ == "__main__":
    unittest.main()
