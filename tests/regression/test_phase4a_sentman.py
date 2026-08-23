from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from panelsolver.core import (
    CommonCasePayload,
    ModelCasePayload,
    PanelFlowState,
    PanelGeometry,
    assemble_common_results,
)
from panelsolver.models import ModelRegistry, SentmanModel

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "phase1"
GOLDEN_ROOT = FIXTURE_ROOT / "golden" / "fmfsolver"
COEFFICIENTS = ("CA", "CY", "CN", "Cl", "Cm", "Cn", "CD", "CL")


def _record_array(record: dict) -> np.ndarray:
    return np.asarray(record["values"]).reshape(record["shape"])


def _npz_array(golden: dict, name: str) -> np.ndarray:
    return _record_array(golden["npz"]["arrays"][name])


def _npz_scalar(golden: dict, name: str) -> float:
    return float(_npz_array(golden, name))


class Phase4aSentmanGoldenTests(unittest.TestCase):
    def test_all_sentman_panel_and_integrated_goldens_match(self) -> None:
        paths = sorted(GOLDEN_ROOT.glob("*.json"))
        paths = [path for path in paths if path.name != "contracts.json"]
        self.assertEqual(6, len(paths))
        registry = ModelRegistry((SentmanModel(),))

        for path in paths:
            with self.subTest(case_id=path.stem):
                golden = json.loads(path.read_text(encoding="utf-8"))
                normalized = golden["normalized_input"]
                geometry = PanelGeometry(
                    centers_stl_m=_npz_array(golden, "centers_stl_m"),
                    normals_out_stl=_npz_array(golden, "normals_out_stl"),
                    areas_m2=_npz_array(golden, "areas_m2"),
                    component_ids=_npz_array(golden, "face_stl_index").astype(
                        np.int64
                    ),
                )
                flow_state = PanelFlowState(
                    velocity_hat_stl=_npz_array(golden, "Vhat_stl"),
                    shielded=_npz_array(golden, "shielded").astype(bool),
                )
                model_case = ModelCasePayload("sentman", normalized)
                loads = registry.evaluate(geometry, flow_state, model_case)
                common_case = CommonCasePayload(
                    case_id=normalized["case_id"],
                    Aref_m2=normalized["Aref_m2"],
                    moment_reference_stl_m=[
                        normalized["ref_x_m"],
                        normalized["ref_y_m"],
                        normalized["ref_z_m"],
                    ],
                    Lref_Cl_m=normalized["Lref_Cl_m"],
                    Lref_Cm_m=normalized["Lref_Cm_m"],
                    Lref_Cn_m=normalized["Lref_Cn_m"],
                    alpha_t_deg=_npz_scalar(golden, "alpha_t_deg_resolved"),
                    beta_t_deg=_npz_scalar(golden, "beta_t_deg_resolved"),
                )
                result = assemble_common_results(
                    common_case,
                    model_case,
                    geometry,
                    flow_state,
                    loads,
                )

                expected_face_force = _record_array(
                    golden["vtp"]["cell_data"]["C_face_stl"]
                )
                actual_face_force = (
                    loads.traction_coeff_stl
                    * (geometry.areas_m2 / common_case.Aref_m2)[:, None]
                )
                np.testing.assert_allclose(
                    actual_face_force,
                    expected_face_force,
                    rtol=0.0,
                    atol=1.0e-10,
                )
                np.testing.assert_allclose(
                    loads.cell_scalars["normal_traction_coeff"],
                    _record_array(golden["vtp"]["cell_data"]["Cp_n"]),
                    rtol=0.0,
                    atol=1.0e-10,
                )
                np.testing.assert_allclose(
                    loads.cell_scalars["theta_deg"],
                    _record_array(golden["vtp"]["cell_data"]["theta_deg"]),
                    rtol=0.0,
                    atol=1.0e-12,
                )
                normal_dot_velocity = np.einsum(
                    "ij,j->i",
                    geometry.normals_out_stl,
                    flow_state.velocity_hat_stl,
                )
                tangent = (
                    flow_state.velocity_hat_stl[None, :]
                    - normal_dot_velocity[:, None] * geometry.normals_out_stl
                )
                tangent_norm = np.linalg.norm(tangent, axis=1)
                tangent_hat = np.zeros_like(tangent)
                defined = tangent_norm > 1.0e-12
                tangent_hat[defined] = tangent[defined] / tangent_norm[defined, None]
                np.testing.assert_allclose(
                    loads.cell_scalars["tangential_traction_coeff"],
                    np.einsum("ij,ij->i", loads.traction_coeff_stl, tangent_hat),
                    rtol=0.0,
                    atol=1.0e-15,
                )
                np.testing.assert_allclose(
                    result.total.force_coeff_stl,
                    _npz_array(golden, "C_force_stl"),
                    rtol=0.0,
                    atol=1.0e-10,
                )
                np.testing.assert_allclose(
                    result.total.force_coeff_body,
                    _npz_array(golden, "C_force_body"),
                    rtol=0.0,
                    atol=1.0e-10,
                )
                np.testing.assert_allclose(
                    result.total.moment_area_coeff_body_m,
                    _npz_array(golden, "C_M_body"),
                    rtol=0.0,
                    atol=1.0e-10,
                )
                for name in COEFFICIENTS:
                    self.assertAlmostEqual(
                        getattr(result.total, name),
                        _npz_scalar(golden, name),
                        delta=1.0e-10,
                        msg=name,
                    )

                rows = golden["csv"]["rows"]
                expected_component_rows = (
                    len(result.components) if len(result.components) > 1 else 0
                )
                self.assertEqual(len(rows) - 1, expected_component_rows)
                if len(rows) > 1:
                    for component, row in zip(result.components, rows[1:], strict=True):
                        self.assertEqual(component.component_id, row["component_id"])
                        for name in COEFFICIENTS:
                            self.assertAlmostEqual(
                                getattr(component.integrated, name),
                                row[name],
                                delta=1.0e-10,
                                msg=f"component {component.component_id} {name}",
                            )

                self.assertEqual(rows[0]["mode"], loads.metadata["mode"])
                self.assertAlmostEqual(
                    rows[0]["out_S"],
                    loads.metadata["S"],
                    delta=1.0e-10,
                )
                self.assertAlmostEqual(
                    rows[0]["out_Ti_K"],
                    loads.metadata["Ti_K"],
                    delta=1.0e-10,
                )
                self.assertEqual(_npz_scalar(golden, "Tw_K"), loads.metadata["Tw_K"])

                if flow_state.shielded.any():
                    np.testing.assert_array_equal(
                        loads.traction_coeff_stl[flow_state.shielded],
                        np.zeros((int(flow_state.shielded.sum()), 3)),
                    )
                    np.testing.assert_array_equal(
                        loads.cell_scalars["normal_traction_coeff"][flow_state.shielded],
                        np.zeros(int(flow_state.shielded.sum())),
                    )


if __name__ == "__main__":
    unittest.main()
