from __future__ import annotations

import os
import tempfile
import unicodedata
import unittest
from pathlib import Path

import numpy as np

import panelsolver
from panelsolver import (
    FMFCase,
    HypersonicCase,
    SolveResult,
    resolve_attitude,
    solve_fmf,
    solve_hypersonic,
)
from panelsolver.core import execute_case
from panelsolver.domains.fmf import adapt_row as adapt_fmf_row
from panelsolver.domains.fmf import read_cases as read_fmf_cases
from panelsolver.domains.hypersonic import adapt_row as adapt_hypersonic_row
from panelsolver.domains.hypersonic import read_cases as read_hypersonic_cases
from tests.current_case_fixtures import read_current_cases

INPUTS = Path(__file__).parents[1] / "fixtures" / "phase1" / "inputs"


def _paths(row) -> tuple[str, ...]:
    return tuple(part.strip() for part in row["stl_path"].split(";") if part.strip())


def _common(row) -> dict[str, object]:
    return {
        "case_id": row["case_id"],
        "stl_paths": _paths(row),
        "stl_scale_m_per_unit": row["stl_scale_m_per_unit"],
        "attitude": resolve_attitude(
            row["alpha_deg"],
            row["beta_or_bank_deg"],
            row["attitude_input"],
        ),
        "Aref_m2": row["Aref_m2"],
        "moment_reference_stl_m": (
            row["ref_x_m"],
            row["ref_y_m"],
            row["ref_z_m"],
        ),
        "Lref_Cl_m": row["Lref_Cl_m"],
        "Lref_Cm_m": row["Lref_Cm_m"],
        "Lref_Cn_m": row["Lref_Cn_m"],
        "shielding": bool(row["shielding_on"]),
        "ray_backend": row["ray_backend"],
    }


class PublicApiTests(unittest.TestCase):
    def test_package_root_has_one_small_explicit_stable_surface(self) -> None:
        self.assertEqual(
            (
                "FMFCase",
                "HypersonicCase",
                "ResolvedAttitude",
                "SolveResult",
                "resolve_attitude",
                "solve_fmf",
                "solve_hypersonic",
            ),
            panelsolver.__all__,
        )
        self.assertNotEqual(FMFCase, HypersonicCase)
        self.assertFalse(hasattr(panelsolver, "SentmanCase"))
        self.assertFalse(hasattr(panelsolver, "solve_sentman"))
        self.assertFalse(hasattr(panelsolver, "CaseExecutionRequest"))
        self.assertFalse(hasattr(panelsolver, "ProductRuntimePolicy"))

    def assert_matches_execution(self, result, compatibility) -> None:
        self.assertIsInstance(result, SolveResult)
        for field in (
            "force_coeff_stl",
            "force_coeff_body",
            "force_coeff_stability",
            "moment_area_coeff_body_m",
            "moment_coeff_body",
        ):
            np.testing.assert_array_equal(
                getattr(compatibility.results.total, field),
                getattr(result.coefficients, field),
            )
        self.assertEqual(len(compatibility.results.components), len(result.components))
        for expected, actual in zip(
            compatibility.results.components,
            result.components,
            strict=True,
        ):
            self.assertEqual(expected.component_id, actual.component_id)
            self.assertEqual(expected.face_count, actual.face_count)
            self.assertEqual(
                expected.shielded_face_count,
                actual.shielded_face_count,
            )
            for field in (
                "force_coeff_stl",
                "force_coeff_body",
                "force_coeff_stability",
                "moment_area_coeff_body_m",
                "moment_coeff_body",
            ):
                np.testing.assert_array_equal(
                    getattr(expected.integrated, field),
                    getattr(actual.integrated, field),
                )
        for field in (
            "centers_stl_m",
            "normals_out_stl",
            "areas_m2",
            "component_ids",
        ):
            np.testing.assert_array_equal(
                getattr(compatibility.results.geometry, field),
                getattr(result.geometry, field),
            )
        np.testing.assert_array_equal(
            compatibility.results.flow_state.velocity_hat_stl,
            result.flow_state.velocity_hat_stl,
        )
        np.testing.assert_array_equal(
            compatibility.shielding.shielded,
            result.flow_state.shielded,
        )
        np.testing.assert_array_equal(
            compatibility.results.local_loads.traction_coeff_stl,
            result.local_loads.traction_coeff_stl,
        )
        self.assertEqual(
            tuple(compatibility.results.local_loads.cell_scalars),
            tuple(result.local_loads.cell_scalars),
        )
        for name in result.local_loads.cell_scalars:
            np.testing.assert_array_equal(
                compatibility.results.local_loads.cell_scalars[name],
                result.local_loads.cell_scalars[name],
            )
        self.assertEqual(
            compatibility.results.local_loads.metadata,
            result.local_loads.metadata,
        )
        self.assertEqual(compatibility.signature.digest, result.case_signature)
        self.assertEqual(
            compatibility.shielding.config.effective_backend,
            result.ray_backend_used,
        )
        self.assertEqual(compatibility.warnings, result.warnings)

    def test_fmf_solve_is_in_memory_and_matches_sentman_pipeline(self) -> None:
        row = read_current_cases(
            read_fmf_cases,
            INPUTS / "fmfsolver_cases.csv",
        ).iloc[0].to_dict()
        case = FMFCase(
            **_common(row),
            speed_ratio=row["S"],
            translational_temperature_k=row["Ti_K"],
            wall_temperature_k=row["Tw_K"],
        )
        compatibility = execute_case(adapt_fmf_row(row).request)
        with tempfile.TemporaryDirectory() as temporary:
            original = os.getcwd()
            os.chdir(temporary)
            try:
                result = solve_fmf(case)
            finally:
                os.chdir(original)
            self.assertEqual([], list(Path(temporary).iterdir()))
        self.assert_matches_execution(result, compatibility)

    def test_hypersonic_solve_is_in_memory_and_matches_compatibility_path(self) -> None:
        row = read_current_cases(
            read_hypersonic_cases,
            INPUTS / "newtsolver_cases.csv",
        ).iloc[0].to_dict()
        case = HypersonicCase(
            **_common(row),
            mach=row["Mach"],
            gamma=row["gamma"],
            windward_equation=row["windward_eq"],
            leeward_equation=row["leeward_eq"],
        )
        compatibility = execute_case(adapt_hypersonic_row(row).request)
        with tempfile.TemporaryDirectory() as temporary:
            original = os.getcwd()
            os.chdir(temporary)
            try:
                result = solve_hypersonic(case)
            finally:
                os.chdir(original)
            self.assertEqual([], list(Path(temporary).iterdir()))
        self.assert_matches_execution(result, compatibility)

    def test_both_case_types_share_portable_case_id_validation(self) -> None:
        fmf_row = read_current_cases(
            read_fmf_cases,
            INPUTS / "fmfsolver_cases.csv",
        ).iloc[0].to_dict()
        hypersonic_row = read_current_cases(
            read_hypersonic_cases,
            INPUTS / "newtsolver_cases.csv",
        ).iloc[0].to_dict()

        def fmf(case_id: str) -> FMFCase:
            common = _common(fmf_row)
            common["case_id"] = case_id
            return FMFCase(
                **common,
                speed_ratio=fmf_row["S"],
                translational_temperature_k=fmf_row["Ti_K"],
                wall_temperature_k=fmf_row["Tw_K"],
            )

        def hypersonic(case_id: str) -> HypersonicCase:
            common = _common(hypersonic_row)
            common["case_id"] = case_id
            return HypersonicCase(
                **common,
                mach=hypersonic_row["Mach"],
                gamma=hypersonic_row["gamma"],
                windward_equation=hypersonic_row["windward_eq"],
                leeward_equation=hypersonic_row["leeward_eq"],
            )

        nfd = "e\N{COMBINING ACUTE ACCENT}-case"
        nfc = unicodedata.normalize("NFC", nfd)
        for factory in (fmf, hypersonic):
            with self.subTest(factory=factory.__name__):
                self.assertEqual("normal-id", factory("normal-id").case_id)
                self.assertEqual(nfc, factory(nfd).case_id)
                for invalid in ("", ".", "..", "a/b", "CON", "name.", "bad\x00id"):
                    with self.subTest(invalid=repr(invalid)), self.assertRaises(
                        ValueError
                    ):
                        factory(invalid)

    def test_nfd_case_id_matches_case_table_signature_for_both_domains(self) -> None:
        nfd = "e\N{COMBINING ACUTE ACCENT}-signature"
        nfc = unicodedata.normalize("NFC", nfd)
        products = (
            (
                read_fmf_cases,
                "fmfsolver_cases.csv",
                adapt_fmf_row,
                FMFCase,
                solve_fmf,
            ),
            (
                read_hypersonic_cases,
                "newtsolver_cases.csv",
                adapt_hypersonic_row,
                HypersonicCase,
                solve_hypersonic,
            ),
        )
        for reader, filename, adapter, case_type, solver in products:
            source = read_current_cases(reader, INPUTS / filename).iloc[[0]].copy()
            source.loc[source.index[0], "case_id"] = nfd
            source.loc[source.index[0], "save_vtp_on"] = 0
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "cases.csv"
                source.to_csv(path, index=False)
                row = reader(path).iloc[0].to_dict()
                self.assertEqual(nfc, row["case_id"])
                common = _common(row)
                common["case_id"] = nfd
                if case_type is FMFCase:
                    case = case_type(
                        **common,
                        speed_ratio=row["S"],
                        translational_temperature_k=row["Ti_K"],
                        wall_temperature_k=row["Tw_K"],
                    )
                else:
                    case = case_type(
                        **common,
                        mach=row["Mach"],
                        gamma=row["gamma"],
                        windward_equation=row["windward_eq"],
                        leeward_equation=row["leeward_eq"],
                    )
                self.assertEqual(nfc, case.case_id)
                compatibility = execute_case(adapter(row).request)
                self.assertEqual(
                    compatibility.signature.digest,
                    solver(case).case_signature,
                )


if __name__ == "__main__":
    unittest.main()
