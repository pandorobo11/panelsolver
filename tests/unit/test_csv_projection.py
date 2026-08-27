import unittest

import numpy as np

from panelsolver.core import (
    CommonCasePayload,
    ContractValueError,
    CsvProjectionPolicy,
    LocalLoads,
    ModelCasePayload,
    PanelFlowState,
    PanelGeometry,
    assemble_common_results,
    project_summary_csv,
)


def fixture():
    geometry = PanelGeometry(
        centers_stl_m=[[0, 0, 0], [1, 0, 0]],
        normals_out_stl=[[1, 0, 0], [1, 0, 0]],
        areas_m2=[1, 1],
        component_ids=[0, 1],
    )
    case = CommonCasePayload(
        case_id="ordered",
        Aref_m2=1,
        moment_reference_stl_m=[0, 0, 0],
        Lref_Cl_m=1,
        Lref_Cm_m=1,
        Lref_Cn_m=1,
        alpha_t_deg=0,
        beta_t_deg=0,
    )
    return assemble_common_results(
        case,
        ModelCasePayload("synthetic"),
        geometry,
        PanelFlowState([1, 0, 0], [False, True]),
        LocalLoads([[1, 0, 0], [0, 0, 0]]),
    )


class CsvProjectionTests(unittest.TestCase):
    def test_orders_input_extras_total_and_component_rows(self) -> None:
        results = fixture()
        policy = CsvProjectionPolicy(
            input_columns=("case_id", "known"),
            result_columns=(
                "label",
                "scope",
                "component_id",
                "component_stl_path",
                "CA",
                "faces",
                "shielded_faces",
                "vtp_path",
            ),
        )

        projection = project_summary_csv(
            {"extra": np.int64(4), "known": "value", "case_id": "ordered"},
            results,
            policy,
            run_values={"label": "run", "vtp_path": "ordered.vtp"},
            component_sources={0: "left.stl", 1: "right.stl"},
        )

        self.assertEqual(
            (
                "case_id",
                "known",
                "extra",
                "label",
                "scope",
                "component_id",
                "component_stl_path",
                "CA",
                "faces",
                "shielded_faces",
                "vtp_path",
            ),
            projection.columns,
        )
        self.assertEqual(
            ["total", "component", "component"], [r["scope"] for r in projection.rows]
        )
        self.assertEqual([None, 0, 1], [r["component_id"] for r in projection.rows])
        self.assertEqual(
            ["ordered.vtp", None, None], [r["vtp_path"] for r in projection.rows]
        )
        self.assertEqual([2, 1, 1], [r["faces"] for r in projection.rows])
        self.assertEqual(4, projection.rows[0]["extra"])
        with self.assertRaises(TypeError):
            projection.rows[0]["scope"] = "changed"  # type: ignore[index]

    def test_rejects_schema_collisions_overrides_and_missing_sources(self) -> None:
        results = fixture()
        with self.assertRaises(ContractValueError):
            CsvProjectionPolicy(("case_id",), ("case_id",))
        policy = CsvProjectionPolicy(("case_id",), ("scope", "label"))
        with self.assertRaises(ContractValueError):
            project_summary_csv(
                {"case_id": "ordered"},
                results,
                policy,
                run_values={"scope": "wrong", "label": "run"},
                component_sources={0: "left.stl", 1: "right.stl"},
            )
        with self.assertRaises(ContractValueError):
            project_summary_csv(
                {"case_id": "ordered"},
                results,
                policy,
                run_values={"label": "run"},
                component_sources={0: "left.stl"},
            )


if __name__ == "__main__":
    unittest.main()
