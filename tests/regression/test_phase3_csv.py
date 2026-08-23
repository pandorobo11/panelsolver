from __future__ import annotations

import json
import unittest
from fnmatch import fnmatchcase
from pathlib import Path

import numpy as np

from panelsolver.core import (
    CommonCasePayload,
    LocalLoads,
    ModelCasePayload,
    PanelFlowState,
    PanelGeometry,
    assemble_common_results,
)
from panelsolver.domains import fmf as fmf_csv
from panelsolver.domains import hypersonic as newt_csv

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "phase1"
GOLDEN_ROOT = FIXTURE_ROOT / "golden"
MANIFEST = json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))
ADAPTERS = {"fmfsolver": fmf_csv, "newtsolver": newt_csv}
CALCULATED_COLUMNS = {
    "alpha_t_deg_resolved",
    "beta_t_deg_resolved",
    "scope",
    "component_id",
    "component_stl_path",
    "CA",
    "CY",
    "CN",
    "Cl",
    "Cm",
    "Cn",
    "CD",
    "CL",
    "faces",
    "shielded_faces",
}


def _record_array(record: dict) -> np.ndarray:
    return np.asarray(record["values"]).reshape(record["shape"])


def _npz_array(golden: dict, name: str) -> np.ndarray:
    return _record_array(golden["npz"]["arrays"][name])


def _profile_tolerance(golden: dict, path: str) -> tuple[float, float]:
    profile = MANIFEST["tolerance_profiles"][golden["provenance"]["tolerance_profile"]]
    tolerance_name = profile["default"]
    matches = {
        override["tolerance"]
        for override in profile.get("path_overrides", [])
        if any(fnmatchcase(path, pattern) for pattern in override["paths"])
    }
    if matches:
        tolerance_name = matches.pop()
    tolerance = MANIFEST["tolerances"][tolerance_name]
    return tolerance["atol"], tolerance["rtol"]


class Phase3CsvGoldenTests(unittest.TestCase):
    def test_both_product_schemas_and_all_semantic_rows_match(self) -> None:
        paths = sorted(GOLDEN_ROOT.glob("*/*.json"))
        paths = [path for path in paths if path.name != "contracts.json"]
        self.assertEqual(15, len(paths))

        for path in paths:
            with self.subTest(solver=path.parent.name, case_id=path.stem):
                golden = json.loads(path.read_text(encoding="utf-8"))
                normalized = golden["normalized_input"]
                current_input = {
                    name: value
                    for name, value in normalized.items()
                    if name != "save_npz_on"
                }
                adapter = ADAPTERS[path.parent.name]
                geometry = PanelGeometry(
                    centers_stl_m=_npz_array(golden, "centers_stl_m"),
                    normals_out_stl=_npz_array(golden, "normals_out_stl"),
                    areas_m2=_npz_array(golden, "areas_m2"),
                    component_ids=_npz_array(golden, "face_stl_index").astype(np.int64),
                )
                face_force = _record_array(golden["vtp"]["cell_data"]["C_face_stl"])
                results = assemble_common_results(
                    CommonCasePayload(
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
                    ),
                    ModelCasePayload(path.parent.name),
                    geometry,
                    PanelFlowState(
                        _npz_array(golden, "Vhat_stl"),
                        _npz_array(golden, "shielded").astype(bool),
                    ),
                    LocalLoads(
                        face_force
                        * (normalized["Aref_m2"] / geometry.areas_m2)[:, None]
                    ),
                )
                expected_rows = [
                    {
                        name: value
                        for name, value in row.items()
                        if name not in {"save_npz_on", "npz_path"}
                    }
                    for row in golden["csv"]["rows"]
                ]
                total_row = expected_rows[0]
                run_values = {
                    name: total_row[name]
                    for name in adapter.CSV_PROJECTION_POLICY.result_columns
                    if name not in CALCULATED_COLUMNS
                }
                sources = {
                    component_id: str(source)
                    for component_id, source in enumerate(
                        _npz_array(golden, "stl_paths").tolist()
                    )
                }

                projection = adapter.project_csv(
                    current_input,
                    results,
                    run_values=run_values,
                    component_sources=sources,
                )

                expected_columns = tuple(
                    name
                    for name in golden["csv"]["columns"]
                    if name not in {"save_npz_on", "npz_path"}
                )
                self.assertEqual(expected_columns, projection.columns)
                self.assertEqual(len(expected_rows), len(projection.rows))
                input_columns = set(current_input)
                for row_index, (expected, actual) in enumerate(
                    zip(expected_rows, projection.rows, strict=True)
                ):
                    self.assertEqual(projection.columns, tuple(actual))
                    for column in projection.columns:
                        expected_value = expected[column]
                        actual_value = actual[column]
                        if isinstance(expected_value, float) and column not in input_columns:
                            atol, rtol = _profile_tolerance(
                                golden,
                                f"csv/rows/{row_index}/{column}",
                            )
                            self.assertTrue(
                                np.isclose(
                                    actual_value,
                                    expected_value,
                                    atol=atol,
                                    rtol=rtol,
                                ),
                                column,
                            )
                        else:
                            self.assertEqual(expected_value, actual_value, column)


if __name__ == "__main__":
    unittest.main()
