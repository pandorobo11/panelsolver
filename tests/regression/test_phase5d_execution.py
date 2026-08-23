from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

import numpy as np

from panelsolver.app import default_model_registry, request_from_registry
from panelsolver.core import (
    CommonCasePayload,
    ModelCasePayload,
    ShieldingConfig,
    execute_case,
)

REPOSITORY_ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "phase1"
GOLDEN_ROOT = FIXTURE_ROOT / "golden"
MANIFEST = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
COEFFICIENTS = ("CA", "CY", "CN", "Cl", "Cm", "Cn", "CD", "CL")


def _record_array(record: dict) -> np.ndarray:
    return np.asarray(record["values"]).reshape(record["shape"])


def _npz_array(golden: dict, name: str) -> np.ndarray:
    return _record_array(golden["npz"]["arrays"][name])


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
    spec = importlib.util.spec_from_file_location("phase5d_comparator", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load the Phase 1 semantic comparator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Phase5dExecutionGoldenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.comparator = _load_comparator_module()

    def test_all_models_and_phase1_cases_run_through_one_engine(self) -> None:
        paths = sorted(GOLDEN_ROOT.glob("*/*.json"))
        paths = [path for path in paths if path.name != "contracts.json"]
        self.assertEqual(15, len(paths))
        registry = default_model_registry()

        for path in paths:
            with self.subTest(solver=path.parent.name, case_id=path.stem):
                golden = json.loads(path.read_text(encoding="utf-8"))
                normalized = golden["normalized_input"]
                model_id = (
                    "sentman" if path.parent.name == "fmfsolver" else "hypersonic"
                )
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
                    alpha_t_deg=float(_npz_array(golden, "alpha_t_deg_resolved")),
                    beta_t_deg=float(_npz_array(golden, "beta_t_deg_resolved")),
                )
                source_names = [
                    Path(value).name
                    for value in str(normalized["stl_path"]).split(";")
                ]
                request = request_from_registry(
                    registry,
                    common_case=common_case,
                    model_case=ModelCasePayload(model_id, normalized),
                    stl_paths=[
                        FIXTURE_ROOT / "inputs" / "stl" / name
                        for name in source_names
                    ],
                    scale_m_per_unit=normalized["stl_scale_m_per_unit"],
                    velocity_hat_stl=_npz_array(golden, "Vhat_stl"),
                    shielding=ShieldingConfig(
                        enabled=bool(normalized["shielding_on"]),
                        ray_backend=normalized["ray_backend"],
                    ),
                )
                execution = execute_case(request)
                result = execution.results
                loads = result.local_loads
                face_force = (
                    loads.traction_coeff_stl
                    * (result.geometry.areas_m2 / common_case.Aref_m2)[:, None]
                )

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
                actual_npz = {
                    "C_force_stl": result.total.force_coeff_stl,
                    "C_force_body": result.total.force_coeff_body,
                    "C_M_body": result.total.moment_area_coeff_body_m,
                    **{
                        name: np.asarray(getattr(result.total, name))
                        for name in COEFFICIENTS
                    },
                }
                legacy_normal_scalar = loads.cell_scalars[
                    "normal_traction_coeff" if model_id == "sentman" else "cp"
                ]
                expected = {
                    "vtp": {
                        "cell_data": {
                            name: golden["vtp"]["cell_data"][name]
                            for name in (
                                "shielded",
                                "C_face_stl",
                                "Cp_n",
                                "theta_deg",
                            )
                        }
                    },
                    "npz": {
                        "arrays": {
                            name: golden["npz"]["arrays"][name]
                            for name in (
                                "C_force_stl",
                                "C_force_body",
                                "C_M_body",
                                *COEFFICIENTS,
                                "Cp_n",
                            )
                        }
                    },
                    "csv": {"rows": expected_rows},
                }
                actual = {
                    "vtp": {
                        "cell_data": {
                            "shielded": _array_record(
                                execution.shielding.shielded.astype(np.uint8)
                            ),
                            "C_face_stl": _array_record(face_force),
                            "Cp_n": _array_record(legacy_normal_scalar),
                            "theta_deg": _array_record(
                                loads.cell_scalars["theta_deg"]
                            ),
                        }
                    },
                    "npz": {
                        "arrays": {
                            **{
                                name: _array_record(actual_npz[name])
                                for name in actual_npz
                            },
                            "Cp_n": _array_record(legacy_normal_scalar),
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
                self.assertEqual(
                    golden["provenance"]["effective_backend"],
                    execution.shielding.config.effective_backend,
                )
                np.testing.assert_array_equal(
                    execution.shielding.shielded,
                    _npz_array(golden, "shielded").astype(bool),
                )
                self.assertEqual(
                    execution.signature.digest,
                    result.metadata["case_signature"],
                )
                if execution.shielding.shielded.any():
                    np.testing.assert_array_equal(
                        loads.traction_coeff_stl[execution.shielding.shielded],
                        np.zeros((int(execution.shielding.shielded.sum()), 3)),
                    )


if __name__ == "__main__":
    unittest.main()
