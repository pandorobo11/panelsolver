import unittest

import numpy as np

from panelsolver.core import (
    CommonCasePayload,
    ContractValueError,
    LocalLoads,
    ModelCasePayload,
    PanelFlowState,
    PanelGeometry,
    aggregate_component_results,
    assemble_common_results,
    integrate_panel_loads,
)


def case() -> CommonCasePayload:
    return CommonCasePayload(
        case_id="components",
        Aref_m2=1.0,
        moment_reference_stl_m=[0, 0, 0],
        Lref_Cl_m=1.0,
        Lref_Cm_m=1.0,
        Lref_Cn_m=1.0,
        alpha_t_deg=0.0,
        beta_t_deg=0.0,
    )


class ComponentAggregationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.geometry = PanelGeometry(
            centers_stl_m=[[0, 0, 0], [1, 0, 0], [2, 0, 0]],
            normals_out_stl=[[1, 0, 0], [1, 0, 0], [1, 0, 0]],
            areas_m2=[1, 1, 1],
            component_ids=[7, 2, 7],
        )
        self.flow = PanelFlowState([1, 0, 0], [False, True, False])
        self.loads = LocalLoads([[1, 0, 0], [0, 0, 0], [3, 0, 0]])

    def test_sparse_components_are_sorted_and_sum_to_total(self) -> None:
        integration = integrate_panel_loads(self.geometry, self.loads, case())
        components = aggregate_component_results(
            self.geometry,
            self.flow,
            integration,
            case(),
            metadata_by_component={7: {"source": "seven"}},
        )

        self.assertEqual((2, 7), tuple(item.component_id for item in components))
        self.assertEqual((1, 2), tuple(item.face_count for item in components))
        self.assertEqual((1, 0), tuple(item.shielded_face_count for item in components))
        np.testing.assert_array_equal(
            components[0].integrated.force_coeff_stl, [0, 0, 0]
        )
        np.testing.assert_array_equal(
            components[1].integrated.force_coeff_stl, [4, 0, 0]
        )
        self.assertEqual("seven", components[1].metadata["source"])
        np.testing.assert_array_equal(
            sum(
                (item.integrated.force_coeff_stl for item in components),
                start=np.zeros(3),
            ),
            integration.total.force_coeff_stl,
        )

    def test_assembler_builds_existing_common_results_contract(self) -> None:
        results = assemble_common_results(
            case(),
            ModelCasePayload("synthetic", {"mode": "test"}),
            self.geometry,
            self.flow,
            self.loads,
            metadata={"run": "unit"},
            metadata_by_component={2: {"name": "two"}},
        )

        self.assertEqual("synthetic", results.model_id)
        self.assertEqual(
            (2, 7), tuple(item.component_id for item in results.components)
        )
        self.assertEqual("unit", results.metadata["run"])
        self.assertEqual("two", results.components[0].metadata["name"])
        np.testing.assert_array_equal(results.total.force_coeff_stl, [4, 0, 0])

    def test_rejects_alignment_and_metadata_errors(self) -> None:
        integration = integrate_panel_loads(self.geometry, self.loads, case())
        short_flow = PanelFlowState([1, 0, 0], [False])
        with self.assertRaises(ContractValueError):
            aggregate_component_results(
                self.geometry,
                short_flow,
                integration,
                case(),
            )
        with self.assertRaises(ContractValueError):
            aggregate_component_results(
                self.geometry,
                self.flow,
                integration,
                case(),
                metadata_by_component={99: {}},
            )
        with self.assertRaises(ContractValueError):
            aggregate_component_results(
                self.geometry,
                self.flow,
                integration,
                case(),
                metadata_by_component={True: {}},
            )


if __name__ == "__main__":
    unittest.main()
