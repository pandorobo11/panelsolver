from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from panelsolver.core import (
    ArtifactProjectionPolicy,
    CommonCasePayload,
    LocalLoads,
    MeshComponent,
    ModelCasePayload,
    PanelFlowState,
    PanelGeometry,
    PanelMesh,
    assemble_common_results,
    project_vtp_artifact,
)

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "phase1"
GOLDEN_ROOT = FIXTURE_ROOT / "golden"
MANIFEST = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
COMMON_VTP_FIELDS = {
    "alpha_t_deg_resolved",
    "attitude_input_used",
    "beta_t_deg_resolved",
    "case_id",
    "case_signature",
    "ray_backend_used",
    "solver_version",
    "stl_count",
    "stl_paths_json",
}
GEOMETRY_CELL_FIELDS = {
    "C_face_stl",
    "area_m2",
    "center_x_stl_m",
    "center_y_stl_m",
    "center_z_stl_m",
    "shielded",
    "stl_index",
}


def _record_array(record: dict) -> np.ndarray:
    return np.asarray(record["values"]).reshape(record["shape"])


def _npz_array(golden: dict, name: str) -> np.ndarray:
    return _record_array(golden["npz"]["arrays"][name])


def _scalar(record: dict) -> object:
    return _record_array(record).item()


def _array_record(value: np.ndarray) -> dict[str, object]:
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


def _tolerance(golden: dict) -> tuple[float, float]:
    profile = MANIFEST["tolerance_profiles"][golden["provenance"]["tolerance_profile"]]
    names = [profile["default"]]
    names.extend(item["tolerance"] for item in profile.get("path_overrides", []))
    values = [MANIFEST["tolerances"][name] for name in names]
    return max(v["atol"] for v in values), max(v["rtol"] for v in values)


class Phase3ArtifactGoldenTests(unittest.TestCase):
    def test_all_vtp_semantic_arrays_match(self) -> None:
        paths = sorted(GOLDEN_ROOT.glob("*/*.json"))
        paths = [path for path in paths if path.name != "contracts.json"]
        self.assertEqual(15, len(paths))

        for path in paths:
            with self.subTest(solver=path.parent.name, case_id=path.stem):
                golden = json.loads(path.read_text(encoding="utf-8"))
                normalized = golden["normalized_input"]
                vtp_records = golden["vtp"]
                geometry = PanelGeometry(
                    centers_stl_m=_npz_array(golden, "centers_stl_m"),
                    normals_out_stl=_npz_array(golden, "normals_out_stl"),
                    areas_m2=_npz_array(golden, "areas_m2"),
                    component_ids=_npz_array(golden, "face_stl_index").astype(np.int64),
                )
                mesh = PanelMesh(
                    _npz_array(golden, "vertices"),
                    _npz_array(golden, "faces").astype(np.int64),
                    geometry,
                    [
                        MeshComponent(component_id, str(source))
                        for component_id, source in enumerate(
                            _npz_array(golden, "stl_paths").tolist()
                        )
                    ],
                )
                face_force = _record_array(vtp_records["cell_data"]["C_face_stl"])
                cell_scalars = {
                    name: _record_array(record)
                    for name, record in vtp_records["cell_data"].items()
                    if name not in GEOMETRY_CELL_FIELDS
                }
                legacy_normal_scalar = cell_scalars.pop("Cp_n")
                if path.parent.name == "fmfsolver":
                    cell_scalars["normal_traction_coeff"] = legacy_normal_scalar
                    velocity = _npz_array(golden, "Vhat_stl")
                    normal_dot_velocity = geometry.normals_out_stl @ velocity
                    tangent = (
                        velocity[None, :]
                        - normal_dot_velocity[:, None] * geometry.normals_out_stl
                    )
                    tangent_norm = np.linalg.norm(tangent, axis=1)
                    tangent_hat = np.zeros_like(tangent)
                    defined = tangent_norm > 1.0e-12
                    tangent_hat[defined] = (
                        tangent[defined] / tangent_norm[defined, None]
                    )
                    traction = face_force * (
                        normalized["Aref_m2"] / geometry.areas_m2
                    )[:, None]
                    cell_scalars["tangential_traction_coeff"] = np.einsum(
                        "ij,ij->i",
                        traction,
                        tangent_hat,
                    )
                else:
                    cell_scalars["cp"] = legacy_normal_scalar
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
                results = assemble_common_results(
                    common_case,
                    ModelCasePayload(path.parent.name),
                    geometry,
                    PanelFlowState(
                        _npz_array(golden, "Vhat_stl"),
                        _npz_array(golden, "shielded").astype(bool),
                    ),
                    LocalLoads(
                        face_force
                        * (normalized["Aref_m2"] / geometry.areas_m2)[:, None],
                        cell_scalars,
                    ),
                )
                field_records = vtp_records["field_data"]
                policy = ArtifactProjectionPolicy(
                    attitude_input_used=str(_scalar(field_records["attitude_input_used"])),
                    case_signature=str(_scalar(field_records["case_signature"])),
                    ray_backend_used=str(_scalar(field_records["ray_backend_used"])),
                    solver_version=str(_scalar(field_records["solver_version"])),
                    vtp_field_data={
                        name: _record_array(record)
                        for name, record in field_records.items()
                        if name not in COMMON_VTP_FIELDS
                    },
                )

                vtp = project_vtp_artifact(mesh, results, policy)
                atol, rtol = _tolerance(golden)
                expected_cell_data = {
                    name: record
                    for name, record in vtp_records["cell_data"].items()
                    if name != "Cp_n"
                }
                if path.parent.name == "fmfsolver":
                    expected_cell_data["normal_traction_coeff"] = vtp_records[
                        "cell_data"
                    ]["Cp_n"]
                    expected_cell_data["tangential_traction_coeff"] = _array_record(
                        cell_scalars["tangential_traction_coeff"]
                    )
                else:
                    expected_cell_data["cp"] = vtp_records["cell_data"]["Cp_n"]
                expected_cell_data = dict(sorted(expected_cell_data.items()))

                self._assert_record(vtp.points, vtp_records["points"], atol, rtol)
                self._assert_record(vtp.faces, vtp_records["faces"], atol, rtol)
                self.assertEqual(list(expected_cell_data), list(vtp.cell_data))
                self.assertEqual(list(vtp_records["field_data"]), list(vtp.field_data))
                for name, record in expected_cell_data.items():
                    self._assert_record(vtp.cell_data[name], record, atol, rtol)
                for name, record in vtp_records["field_data"].items():
                    self._assert_record(vtp.field_data[name], record, atol, rtol)

    def _assert_record(
        self,
        actual: np.ndarray,
        record: dict,
        atol: float,
        rtol: float,
    ) -> None:
        expected = _record_array(record)
        self.assertEqual(tuple(record["shape"]), actual.shape)
        expected_kind = record["dtype"]
        actual_kind = {
            "b": "bool",
            "i": f"int{actual.dtype.itemsize * 8}",
            "u": f"uint{actual.dtype.itemsize * 8}",
            "f": f"float{actual.dtype.itemsize * 8}",
            "U": "string",
            "S": "string",
        }[actual.dtype.kind]
        self.assertEqual(expected_kind, actual_kind)
        if actual.dtype.kind == "f":
            np.testing.assert_allclose(actual, expected, atol=atol, rtol=rtol)
        else:
            np.testing.assert_array_equal(actual, expected)


if __name__ == "__main__":
    unittest.main()
