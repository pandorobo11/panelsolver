from __future__ import annotations

import pickle
import unittest
from dataclasses import FrozenInstanceError

import numpy as np

from panelsolver.core import (
    CommonCasePayload,
    CommonResults,
    ComponentResult,
    ContractError,
    ContractValueError,
    IntegratedCoefficients,
    LocalLoads,
    ModelCasePayload,
    NonFiniteError,
    PanelFlowState,
    PanelGeometry,
    PanelSolverError,
    ShapeError,
)


def panel_geometry() -> PanelGeometry:
    return PanelGeometry(
        centers_stl_m=np.array([[0.0, 0.0, 0.0], [1.0, 0.5, -0.5]]),
        normals_out_stl=np.array([[-1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]),
        areas_m2=np.array([1.0, 2.0]),
        component_ids=np.array([0, 1], dtype=np.int32),
    )


def flow_state(*, shielded: tuple[bool, bool] = (False, True)) -> PanelFlowState:
    return PanelFlowState(
        velocity_hat_stl=np.array([1.0, 0.0, 0.0]),
        shielded=np.array(shielded, dtype=bool),
    )


def common_case() -> CommonCasePayload:
    return CommonCasePayload(
        case_id="synthetic-ケース",
        Aref_m2=2.0,
        moment_reference_stl_m=np.array([0.1, -0.2, 0.3]),
        Lref_Cl_m=1.0,
        Lref_Cm_m=2.0,
        Lref_Cn_m=3.0,
        alpha_t_deg=90.0,
        beta_t_deg=-90.0,
    )


def integrated(seed: float = 1.0) -> IntegratedCoefficients:
    return IntegratedCoefficients(
        force_coeff_stl=np.array([seed, seed + 1.0, seed + 2.0]),
        force_coeff_body=np.array([-seed, seed + 1.0, -(seed + 2.0)]),
        force_coeff_stability=np.array([-(seed + 3.0), seed + 1.0, -(seed + 4.0)]),
        moment_area_coeff_body_m=np.array([seed + 5.0, seed + 6.0, seed + 7.0]),
        moment_coeff_body=np.array([seed + 8.0, seed + 9.0, seed + 10.0]),
    )


class ArrayOwnershipTests(unittest.TestCase):
    def test_contracts_take_private_immutable_array_copies(self) -> None:
        centers = np.array([[0.0, 0.0, 0.0]])
        normals = np.array([[-1.0, 0.0, 0.0]])
        areas = np.array([1.0])
        components = np.array([0], dtype=np.int32)
        geometry = PanelGeometry(centers, normals, areas, components)

        centers[0, 0] = 99.0
        normals[0, 0] = 0.0
        areas[0] = 99.0
        components[0] = 99

        np.testing.assert_array_equal(
            geometry.centers_stl_m,
            np.array([[0.0, 0.0, 0.0]]),
        )
        np.testing.assert_array_equal(
            geometry.normals_out_stl,
            np.array([[-1.0, 0.0, 0.0]]),
        )
        np.testing.assert_array_equal(geometry.areas_m2, np.array([1.0]))
        np.testing.assert_array_equal(geometry.component_ids, np.array([0]))

        for array in (
            geometry.centers_stl_m,
            geometry.normals_out_stl,
            geometry.areas_m2,
            geometry.component_ids,
        ):
            with self.subTest(dtype=array.dtype):
                self.assertTrue(array.flags.c_contiguous)
                self.assertFalse(array.flags.writeable)
                with self.assertRaises(ValueError):
                    array.flat[0] = 4
                with self.assertRaises(ValueError):
                    array.setflags(write=True)

        for source, retained in (
            (centers, geometry.centers_stl_m),
            (normals, geometry.normals_out_stl),
            (areas, geometry.areas_m2),
            (components, geometry.component_ids),
        ):
            self.assertFalse(np.shares_memory(source, retained))

        with self.assertRaises(FrozenInstanceError):
            geometry.areas_m2 = np.array([2.0])

    def test_nested_payloads_are_copied_and_deeply_frozen(self) -> None:
        payload = {
            "flow": {"selectors": ["newtonian", "tangent_cone"]},
            "mach": np.float64(8.0),
        }
        case = ModelCasePayload(model_id="synthetic", payload=payload)
        payload["flow"]["selectors"].append("changed")
        payload["mach"] = 99.0

        self.assertEqual(
            ("newtonian", "tangent_cone"),
            case.payload["flow"]["selectors"],
        )
        self.assertEqual(8.0, case.payload["mach"])
        with self.assertRaises(TypeError):
            case.payload["extra"] = True
        with self.assertRaises(TypeError):
            case.payload["flow"]["extra"] = True

    def test_pickle_round_trip_preserves_contract_immutability(self) -> None:
        original = LocalLoads(
            traction_coeff_stl=np.array([[-2.0, 0.25, 0.0]]),
            cell_scalars={"cp": np.array([2.0])},
            metadata={"equations": ["synthetic"]},
        )
        restored = pickle.loads(pickle.dumps(original))

        np.testing.assert_array_equal(
            original.traction_coeff_stl,
            restored.traction_coeff_stl,
        )
        self.assertFalse(restored.traction_coeff_stl.flags.writeable)
        self.assertEqual(("synthetic",), restored.metadata["equations"])


class GeometryAndFlowValidationTests(unittest.TestCase):
    def test_geometry_exposes_shape_and_component_identity(self) -> None:
        geometry = panel_geometry()
        self.assertEqual(2, geometry.n_faces)
        self.assertEqual((0, 1), geometry.unique_component_ids)
        self.assertEqual(np.dtype(np.float64), geometry.centers_stl_m.dtype)
        self.assertEqual(np.dtype(np.int64), geometry.component_ids.dtype)

    def test_geometry_rejects_shape_nonfinite_and_invalid_values(self) -> None:
        valid = {
            "centers_stl_m": np.zeros((2, 3)),
            "normals_out_stl": np.array([[-1.0, 0.0, 0.0]] * 2),
            "areas_m2": np.ones(2),
            "component_ids": np.array([0, 0]),
        }
        cases = (
            (
                "centers shape",
                {**valid, "centers_stl_m": np.zeros((2, 2))},
                ShapeError,
            ),
            (
                "normal count",
                {**valid, "normals_out_stl": np.array([[-1.0, 0.0, 0.0]])},
                ShapeError,
            ),
            (
                "nonfinite center",
                {**valid, "centers_stl_m": np.array([[np.nan, 0, 0], [0, 0, 0]])},
                NonFiniteError,
            ),
            (
                "non-unit normal",
                {**valid, "normals_out_stl": np.array([[-2.0, 0.0, 0.0]] * 2)},
                ContractValueError,
            ),
            (
                "zero area",
                {**valid, "areas_m2": np.array([1.0, 0.0])},
                ContractValueError,
            ),
            (
                "float component",
                {**valid, "component_ids": np.array([0.0, 1.0])},
                ContractValueError,
            ),
            (
                "negative component",
                {**valid, "component_ids": np.array([0, -1])},
                ContractValueError,
            ),
            (
                "empty geometry",
                {
                    "centers_stl_m": np.empty((0, 3)),
                    "normals_out_stl": np.empty((0, 3)),
                    "areas_m2": np.empty(0),
                    "component_ids": np.empty(0, dtype=int),
                },
                ContractValueError,
            ),
        )
        for name, values, expected_error in cases:
            with self.subTest(name=name), self.assertRaises(expected_error):
                PanelGeometry(**values)

    def test_flow_state_requires_unit_velocity_and_strict_boolean_mask(self) -> None:
        state = flow_state()
        self.assertEqual(2, state.n_faces)
        self.assertFalse(state.velocity_hat_stl.flags.writeable)
        self.assertFalse(state.shielded.flags.writeable)

        invalid = (
            (np.array([1.0, 0.0]), np.array([False, True]), ShapeError),
            (np.array([2.0, 0.0, 0.0]), np.array([False, True]), ContractValueError),
            (np.array([np.inf, 0.0, 0.0]), np.array([False, True]), NonFiniteError),
            (np.array([1.0, 0.0, 0.0]), np.array([0, 1]), ContractValueError),
            (np.array([1.0, 0.0, 0.0]), np.empty(0, dtype=bool), ContractValueError),
        )
        for velocity, shielded, expected_error in invalid:
            with (
                self.subTest(
                    velocity=velocity,
                    shielded=shielded,
                ),
                self.assertRaises(expected_error),
            ):
                PanelFlowState(velocity_hat_stl=velocity, shielded=shielded)

    def test_array_coercion_errors_are_field_aware_contract_errors(self) -> None:
        valid_geometry = {
            "centers_stl_m": [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]],
            "normals_out_stl": [[-1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]],
            "areas_m2": [1.0, 1.0],
            "component_ids": [0, 0],
        }

        class TypeErrorArray:
            def __array__(self, *_args: object, **_kwargs: object) -> np.ndarray:
                raise TypeError("synthetic array coercion failure")

        cases = (
            (
                lambda: PanelGeometry(
                    **{
                        **valid_geometry,
                        "centers_stl_m": [[0.0, 0.0, 0.0], [1.0]],
                    }
                ),
                "PanelGeometry.centers_stl_m",
            ),
            (
                lambda: PanelGeometry(
                    **{**valid_geometry, "component_ids": [[0], [0, 1]]}
                ),
                "PanelGeometry.component_ids",
            ),
            (
                lambda: PanelFlowState(
                    velocity_hat_stl=[1.0, 0.0, 0.0],
                    shielded=[[False], [True, False]],
                ),
                "PanelFlowState.shielded",
            ),
            (
                lambda: LocalLoads(
                    traction_coeff_stl=[[1.0, 0.0, 0.0], [1.0]],
                ),
                "LocalLoads.traction_coeff_stl",
            ),
            (
                lambda: LocalLoads(
                    traction_coeff_stl=np.zeros((2, 3)),
                    cell_scalars={"cp": [[1.0], [2.0, 3.0]]},
                ),
                "LocalLoads.cell_scalars.cp",
            ),
            (
                lambda: PanelGeometry(
                    **{**valid_geometry, "areas_m2": TypeErrorArray()}
                ),
                "PanelGeometry.areas_m2",
            ),
        )
        for construct, field in cases:
            with (
                self.subTest(field=field),
                self.assertRaises(ContractValueError) as caught,
            ):
                construct()
            self.assertEqual(field, caught.exception.field)


class LocalLoadsTests(unittest.TestCase):
    def test_vector_contract_retains_tangential_and_normal_loads(self) -> None:
        traction = np.array([[-2.0, 0.5, 0.0], [-1.0, 0.0, 0.0]])
        cp = np.array([2.0, 1.0])
        loads = LocalLoads(
            traction_coeff_stl=traction,
            cell_scalars={"cp": cp, "windward": np.array([True, True])},
            metadata={"family": "synthetic", "selectors": ["a", "b"]},
        )

        self.assertEqual((2, 3), loads.traction_coeff_stl.shape)
        self.assertEqual((2,), loads.cell_scalars["cp"].shape)
        self.assertEqual(np.dtype(np.bool_), loads.cell_scalars["windward"].dtype)
        self.assertEqual(0.5, loads.traction_coeff_stl[0, 1])
        self.assertEqual(("a", "b"), loads.metadata["selectors"])

        traction[0, 1] = 99.0
        cp[0] = 99.0
        self.assertEqual(0.5, loads.traction_coeff_stl[0, 1])
        self.assertEqual(2.0, loads.cell_scalars["cp"][0])

    def test_local_loads_validate_vector_scalars_and_metadata(self) -> None:
        cases = (
            (
                {"traction_coeff_stl": np.ones((2, 2))},
                ShapeError,
            ),
            (
                {"traction_coeff_stl": np.array([[np.nan, 0.0, 0.0]])},
                NonFiniteError,
            ),
            (
                {
                    "traction_coeff_stl": np.zeros((2, 3)),
                    "cell_scalars": {"cp": np.ones(1)},
                },
                ShapeError,
            ),
            (
                {
                    "traction_coeff_stl": np.zeros((1, 3)),
                    "cell_scalars": {"cp": np.array([np.inf])},
                },
                NonFiniteError,
            ),
            (
                {
                    "traction_coeff_stl": np.zeros((1, 3)),
                    "cell_scalars": {"label": np.array(["windward"])},
                },
                ContractValueError,
            ),
            (
                {
                    "traction_coeff_stl": np.zeros((1, 3)),
                    "metadata": {"bad": np.nan},
                },
                NonFiniteError,
            ),
            (
                {
                    "traction_coeff_stl": np.zeros((1, 3)),
                    "metadata": {"bad": np.array([1.0])},
                },
                ContractValueError,
            ),
        )
        for values, expected_error in cases:
            with self.subTest(values=values), self.assertRaises(expected_error):
                LocalLoads(**values)

    def test_payload_cycles_are_rejected(self) -> None:
        cycle: list[object] = []
        cycle.append(cycle)
        with self.assertRaises(ContractValueError):
            ModelCasePayload(model_id="synthetic", payload={"cycle": cycle})


class CaseAndResultTests(unittest.TestCase):
    def test_common_case_validates_only_shared_numerical_rules(self) -> None:
        case = common_case()
        self.assertEqual("synthetic-ケース", case.case_id)
        self.assertEqual(90.0, case.alpha_t_deg)
        self.assertEqual(-90.0, case.beta_t_deg)
        self.assertFalse(case.moment_reference_stl_m.flags.writeable)

        invalid = (
            ({"Aref_m2": 0.0}, ContractValueError),
            ({"Lref_Cm_m": -1.0}, ContractValueError),
            ({"alpha_t_deg": np.inf}, NonFiniteError),
            ({"moment_reference_stl_m": np.zeros(2)}, ShapeError),
            ({"Aref_m2": True}, ContractValueError),
            ({"case_id": " spaced "}, ContractValueError),
        )
        base = {
            "case_id": "case",
            "Aref_m2": 1.0,
            "moment_reference_stl_m": np.zeros(3),
            "Lref_Cl_m": 1.0,
            "Lref_Cm_m": 1.0,
            "Lref_Cn_m": 1.0,
            "alpha_t_deg": 0.0,
            "beta_t_deg": 0.0,
        }
        for update, expected_error in invalid:
            with self.subTest(update=update), self.assertRaises(expected_error):
                CommonCasePayload(**{**base, **update})

    def test_integrated_result_retains_frames_and_eight_coefficients(self) -> None:
        result = integrated()
        expected = {
            "CA": 1.0,
            "CY": 2.0,
            "CN": 3.0,
            "Cl": 9.0,
            "Cm": 10.0,
            "Cn": 11.0,
            "CD": 4.0,
            "CL": 5.0,
        }
        for name, value in expected.items():
            with self.subTest(name=name):
                self.assertEqual(value, getattr(result, name))
        for name in (
            "force_coeff_stl",
            "force_coeff_body",
            "force_coeff_stability",
            "moment_area_coeff_body_m",
            "moment_coeff_body",
        ):
            self.assertFalse(getattr(result, name).flags.writeable)

    def test_common_results_validate_panel_and_component_alignment(self) -> None:
        geometry = panel_geometry()
        state = flow_state()
        local = LocalLoads(
            traction_coeff_stl=np.array([[-2.0, 0.25, 0.0], [0.0, 0.0, 0.0]]),
            metadata={"mode": "synthetic"},
        )
        components = (
            ComponentResult(
                component_id=0,
                integrated=integrated(0.0),
                face_count=1,
                shielded_face_count=0,
            ),
            ComponentResult(
                component_id=1,
                integrated=integrated(1.0),
                face_count=1,
                shielded_face_count=1,
                metadata={"source": "component-b"},
            ),
        )
        result = CommonResults(
            case=common_case(),
            model_case=ModelCasePayload("synthetic", {"speed": 4.0}),
            geometry=geometry,
            flow_state=state,
            local_loads=local,
            total=integrated(2.0),
            components=components,
            metadata={"backend": "not_used"},
        )

        self.assertEqual("synthetic", result.model_id)
        self.assertEqual((0, 1), tuple(item.component_id for item in result.components))
        self.assertEqual("component-b", result.components[1].metadata["source"])

        wrong_components = (
            ComponentResult(0, integrated(), 1, 0),
            ComponentResult(2, integrated(), 1, 1),
        )
        with self.assertRaises(ContractValueError):
            CommonResults(
                case=common_case(),
                model_case=ModelCasePayload("synthetic"),
                geometry=geometry,
                flow_state=state,
                local_loads=local,
                total=integrated(),
                components=wrong_components,
            )

        wrong_count = (
            ComponentResult(0, integrated(), 2, 0),
            ComponentResult(1, integrated(), 1, 1),
        )
        with self.assertRaises(ContractValueError):
            CommonResults(
                case=common_case(),
                model_case=ModelCasePayload("synthetic"),
                geometry=geometry,
                flow_state=state,
                local_loads=local,
                total=integrated(),
                components=wrong_count,
            )

        with self.assertRaises(ContractValueError):
            CommonResults(
                case=common_case(),
                model_case=ModelCasePayload("synthetic"),
                geometry=geometry,
                flow_state=state,
                local_loads=LocalLoads(np.ones((2, 3))),
                total=integrated(),
                components=components,
            )

    def test_error_taxonomy_is_stable_and_field_aware(self) -> None:
        self.assertTrue(issubclass(ContractError, PanelSolverError))
        self.assertTrue(issubclass(ContractError, ValueError))
        with self.assertRaises(ShapeError) as caught:
            PanelFlowState(np.zeros(2), np.array([False]))
        self.assertEqual("PanelFlowState.velocity_hat_stl", caught.exception.field)
        self.assertEqual((3,), caught.exception.expected)
        self.assertEqual((2,), caught.exception.actual)


if __name__ == "__main__":
    unittest.main()
