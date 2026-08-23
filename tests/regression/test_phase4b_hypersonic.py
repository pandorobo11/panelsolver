from __future__ import annotations

import importlib.util
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
from panelsolver.models import HypersonicModel, ModelRegistry

REPOSITORY_ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "phase1"
GOLDEN_ROOT = FIXTURE_ROOT / "golden" / "newtsolver"
MANIFEST = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
COEFFICIENTS = ("CA", "CY", "CN", "Cl", "Cm", "Cn", "CD", "CL")


def _record_array(record: dict) -> np.ndarray:
    return np.asarray(record["values"]).reshape(record["shape"])


def _npz_array(golden: dict, name: str) -> np.ndarray:
    return _record_array(golden["npz"]["arrays"][name])


def _npz_scalar(golden: dict, name: str) -> float:
    return float(_npz_array(golden, name))


def _array_record(value: np.ndarray) -> dict:
    array = np.asarray(value)
    logical_dtype = {
        "b": "bool",
        "i": f"int{array.dtype.itemsize * 8}",
        "u": f"uint{array.dtype.itemsize * 8}",
        "f": f"float{array.dtype.itemsize * 8}",
    }[array.dtype.kind]
    return {
        "dtype": logical_dtype,
        "shape": list(array.shape),
        "values": array.tolist(),
    }


def _load_comparator_module():
    script = REPOSITORY_ROOT / "scripts" / "generate_phase1_goldens.py"
    spec = importlib.util.spec_from_file_location("phase4b_comparator", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the Phase 1 semantic comparator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Phase4bHypersonicGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.comparator = _load_comparator_module()

    def test_all_hypersonic_panel_and_integrated_goldens_match(self) -> None:
        paths = sorted(GOLDEN_ROOT.glob("*.json"))
        paths = [path for path in paths if path.name != "contracts.json"]
        self.assertEqual(9, len(paths))
        registry = ModelRegistry((HypersonicModel(),))

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
                model_case = ModelCasePayload("hypersonic", normalized)
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
                face_force = (
                    loads.traction_coeff_stl
                    * (geometry.areas_m2 / common_case.Aref_m2)[:, None]
                )

                npz_names = (
                    "C_force_stl",
                    "C_force_body",
                    "C_M_body",
                    *COEFFICIENTS,
                )
                actual_npz_values = {
                    "C_force_stl": result.total.force_coeff_stl,
                    "C_force_body": result.total.force_coeff_body,
                    "C_M_body": result.total.moment_area_coeff_body_m,
                    **{
                        name: np.asarray(getattr(result.total, name))
                        for name in COEFFICIENTS
                    },
                }
                expected_rows = [
                    {name: row[name] for name in COEFFICIENTS}
                    for row in golden["csv"]["rows"]
                ]
                actual_rows = [
                    {name: getattr(result.total, name) for name in COEFFICIENTS}
                ]
                if len(expected_rows) > 1:
                    actual_rows.extend(
                        {
                            name: getattr(component.integrated, name)
                            for name in COEFFICIENTS
                        }
                        for component in result.components
                    )
                expected = {
                    "vtp": {
                        "cell_data": {
                            name: golden["vtp"]["cell_data"][name]
                            for name in ("C_face_stl", "Cp_n", "theta_deg")
                        }
                    },
                    "npz": {
                        "arrays": {
                            name: golden["npz"]["arrays"][name]
                            for name in (*npz_names, "Cp_n")
                        }
                    },
                    "csv": {"rows": expected_rows},
                }
                actual = {
                    "vtp": {
                        "cell_data": {
                            "C_face_stl": _array_record(face_force),
                            "Cp_n": _array_record(loads.cell_scalars["cp"]),
                            "theta_deg": _array_record(
                                loads.cell_scalars["theta_deg"]
                            ),
                        }
                    },
                    "npz": {
                        "arrays": {
                            **{
                                name: _array_record(actual_npz_values[name])
                                for name in npz_names
                            },
                            "Cp_n": _array_record(loads.cell_scalars["cp"]),
                        }
                    },
                    "csv": {"rows": actual_rows},
                }
                differences = self.comparator._compare_values(
                    expected,
                    actual,
                    manifest=MANIFEST,
                    profile_name=golden["provenance"]["tolerance_profile"],
                )
                self.assertEqual([], differences)

                field_data = golden["vtp"]["field_data"]
                expected_windward = str(
                    _record_array(field_data["windward_eq_used"]).item()
                )
                expected_leeward = str(
                    _record_array(field_data["leeward_eq_used"]).item()
                )
                self.assertEqual(
                    expected_windward,
                    loads.metadata["windward_eq"],
                )
                self.assertEqual(
                    expected_leeward,
                    loads.metadata["leeward_eq"],
                )
                self.assertEqual(normalized["Mach"], loads.metadata["Mach"])
                self.assertEqual(normalized["gamma"], loads.metadata["gamma"])

                if flow_state.shielded.any():
                    np.testing.assert_array_equal(
                        loads.traction_coeff_stl[flow_state.shielded],
                        np.zeros((int(flow_state.shielded.sum()), 3)),
                    )
                    np.testing.assert_array_equal(
                        loads.cell_scalars["cp"][flow_state.shielded],
                        np.zeros(int(flow_state.shielded.sum())),
                    )


if __name__ == "__main__":
    unittest.main()
