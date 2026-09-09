import unittest

import numpy as np

from panelsolver.core import (
    CommonCasePayload,
    ContractValueError,
    LocalLoads,
    PanelGeometry,
    integrate_panel_loads,
)


def case(*, reference: object = (0.0, 0.0, 0.0)) -> CommonCasePayload:
    return CommonCasePayload(
        case_id="synthetic",
        Aref_m2=1.0,
        moment_reference_stl_m=reference,
        Lref_Cl_m=2.0,
        Lref_Cm_m=1.0,
        Lref_Cn_m=1.0,
        alpha_stability_deg=0.0,
    )


class PanelIntegrationTests(unittest.TestCase):
    def test_integrates_force_moment_frames_and_public_coefficients(self) -> None:
        geometry = PanelGeometry(
            centers_stl_m=[[1, 0, 0], [0, 1, 0]],
            normals_out_stl=[[0, 0, 1], [0, 0, 1]],
            areas_m2=[1, 1],
            component_ids=[0, 0],
        )
        loads = LocalLoads([[1, 0, 0], [0, 0, 1]])

        result = integrate_panel_loads(geometry, loads, case())

        np.testing.assert_array_equal(
            result.face_force_coeff_stl,
            [[1, 0, 0], [0, 0, 1]],
        )
        np.testing.assert_array_equal(
            result.face_moment_area_coeff_body_m,
            [[0, 0, 0], [-1, 0, 0]],
        )
        np.testing.assert_array_equal(result.total.force_coeff_stl, [1, 0, 1])
        np.testing.assert_array_equal(result.total.force_coeff_body, [-1, 0, -1])
        np.testing.assert_array_equal(
            result.total.force_coeff_stability,
            [-1, 0, -1],
        )
        np.testing.assert_array_equal(
            result.total.moment_area_coeff_body_m,
            [-1, 0, 0],
        )
        np.testing.assert_array_equal(result.total.moment_coeff_body, [-0.5, 0, 0])
        self.assertEqual(1.0, result.total.CA)
        self.assertEqual(0.0, result.total.CY)
        self.assertEqual(1.0, result.total.CN)
        self.assertEqual(-0.5, result.total.Cl)
        self.assertEqual(0.0, result.total.Cm)
        self.assertEqual(0.0, result.total.Cn)
        self.assertEqual(1.0, result.total.CD)
        self.assertEqual(1.0, result.total.CL)
        self.assertEqual(2, result.n_faces)
        self.assertFalse(result.face_force_coeff_stl.flags.writeable)

    def test_applies_area_and_reference_area_exactly_once(self) -> None:
        geometry = PanelGeometry(
            centers_stl_m=[[0, 0, 0], [0, 0, 0]],
            normals_out_stl=[[1, 0, 0], [1, 0, 0]],
            areas_m2=[2, 4],
            component_ids=[0, 0],
        )
        loads = LocalLoads([[3, 0, 0], [3, 0, 0]])
        scaled_case = CommonCasePayload(
            case_id="scaled",
            Aref_m2=2.0,
            moment_reference_stl_m=[0, 0, 0],
            Lref_Cl_m=1.0,
            Lref_Cm_m=1.0,
            Lref_Cn_m=1.0,
            alpha_stability_deg=0.0,
        )

        result = integrate_panel_loads(geometry, loads, scaled_case)

        np.testing.assert_array_equal(
            result.face_force_coeff_stl,
            [[3, 0, 0], [6, 0, 0]],
        )
        np.testing.assert_array_equal(result.total.force_coeff_stl, [9, 0, 0])

    def test_reference_point_and_axis_lengths_normalize_body_moment(self) -> None:
        geometry = PanelGeometry(
            centers_stl_m=[[1, 0, 0]],
            normals_out_stl=[[0, 0, 1]],
            areas_m2=[1],
            component_ids=[0],
        )
        result = integrate_panel_loads(
            geometry,
            LocalLoads([[0, 0, 1]]),
            case(reference=(0.5, 0, 0)),
        )
        np.testing.assert_array_equal(
            result.total.moment_area_coeff_body_m,
            [0, -0.5, 0],
        )
        np.testing.assert_array_equal(result.total.moment_coeff_body, [0, -0.5, 0])

    def test_rejects_type_and_panel_count_mismatches(self) -> None:
        geometry = PanelGeometry(
            centers_stl_m=[[0, 0, 0]],
            normals_out_stl=[[1, 0, 0]],
            areas_m2=[1],
            component_ids=[0],
        )
        loads = LocalLoads([[1, 0, 0], [1, 0, 0]])
        with self.assertRaises(ContractValueError):
            integrate_panel_loads(geometry, loads, case())
        with self.assertRaises(ContractValueError):
            integrate_panel_loads(object(), loads, case())
        with self.assertRaises(ContractValueError):
            integrate_panel_loads(geometry, object(), case())
        with self.assertRaises(ContractValueError):
            integrate_panel_loads(geometry, LocalLoads([[1, 0, 0]]), object())


if __name__ == "__main__":
    unittest.main()
