from __future__ import annotations

import math
import unittest

import numpy as np

from panelsolver.core import (
    CommonCasePayload,
    ModelCasePayload,
    PanelFlowState,
    PanelGeometry,
    PanelLoadModel,
    integrate_panel_loads,
)
from panelsolver.core.execution import SchedulingAffinityProvider
from panelsolver.models import (
    HypersonicCaseError,
    HypersonicModel,
    ModelRegistry,
)
from panelsolver.models.hypersonic import (
    _inverse_prandtl_meyer,
    _prandtl_meyer_nu,
    _tangent_cone_detach_limit,
    _tangent_wedge_detach_limit,
    modified_newtonian_cp_max,
    prandtl_meyer_pressure_coefficient,
    tangent_cone_pressure_coefficient,
    tangent_wedge_pressure_coefficient,
)


def _geometry(
    normals: np.ndarray,
    component_ids: np.ndarray | None = None,
) -> PanelGeometry:
    n_faces = normals.shape[0]
    return PanelGeometry(
        centers_stl_m=np.zeros((n_faces, 3)),
        normals_out_stl=normals,
        areas_m2=np.ones(n_faces),
        component_ids=(
            np.zeros(n_faces, dtype=np.int64)
            if component_ids is None
            else component_ids
        ),
    )


def _case(**updates: object) -> ModelCasePayload:
    payload: dict[str, object] = {
        "Mach": 6.0,
        "gamma": 1.4,
        "windward_eq": "newtonian",
        "leeward_eq": "shield",
    }
    payload.update(updates)
    return ModelCasePayload("hypersonic", payload)


class HypersonicModelTests(unittest.TestCase):
    def test_model_implements_protocol_and_returns_pressure_normal_load(self) -> None:
        model = HypersonicModel()
        self.assertIsInstance(model, PanelLoadModel)
        self.assertIsInstance(model, SchedulingAffinityProvider)
        geometry = _geometry(np.array([[-1.0, 0.0, 0.0]]))
        loads = ModelRegistry((model,)).evaluate(
            geometry,
            PanelFlowState(
                np.array([1.0, 0.0, 0.0]),
                np.array([False]),
            ),
            _case(),
        )

        np.testing.assert_array_equal(
            np.cross(loads.traction_coeff_stl, geometry.normals_out_stl),
            np.zeros((1, 3)),
        )
        np.testing.assert_array_equal(
            loads.traction_coeff_stl,
            np.array([[2.0, 0.0, 0.0]]),
        )
        self.assertEqual(("cp", "theta_deg"), tuple(loads.cell_scalars))
        self.assertNotIn("Cp_n", loads.cell_scalars)
        np.testing.assert_array_equal(
            loads.traction_coeff_stl,
            -loads.cell_scalars["cp"][:, None] * geometry.normals_out_stl,
        )

    def test_scheduling_affinities_match_selected_model_cache_inputs(self) -> None:
        model = HypersonicModel()
        mach = float(np.nextafter(5.0, 6.0))
        mixed = model.scheduling_affinities(
            _case(
                Mach=mach,
                gamma=1.4,
                windward_eq="tangent_wedge;tangent_cone",
            )
        )
        self.assertEqual(
            [
                ("tangent_cone", mach, 1.4),
                ("tangent_wedge", mach, 1.4),
            ],
            [hint.identity for hint in mixed],
        )
        self.assertGreater(mixed[0].priority, mixed[1].priority)

        for windward, leeward in (
            ("newtonian", "shield"),
            ("modified_newtonian", "shield"),
            ("newtonian", "prandtl_meyer"),
        ):
            with self.subTest(windward=windward, leeward=leeward):
                self.assertEqual(
                    (),
                    model.scheduling_affinities(
                        _case(windward_eq=windward, leeward_eq=leeward)
                    ),
                )

    def test_newtonian_flat_plate_matches_independent_reference(self) -> None:
        model = HypersonicModel()
        geometry = _geometry(np.array([[-1.0, 0.0, 0.0]]))
        for alpha_deg in (0.0, 10.0, 30.0, 60.0):
            alpha_rad = math.radians(alpha_deg)
            flow = PanelFlowState(
                np.array([math.cos(alpha_rad), 0.0, math.sin(alpha_rad)]),
                np.array([False]),
            )
            loads = model.evaluate(geometry, flow, _case())
            integrated = integrate_panel_loads(
                geometry,
                loads,
                CommonCasePayload(
                    case_id="flat-plate",
                    Aref_m2=1.0,
                    moment_reference_stl_m=np.zeros(3),
                    Lref_Cl_m=1.0,
                    Lref_Cm_m=1.0,
                    Lref_Cn_m=1.0,
                    alpha_t_deg=alpha_deg,
                    beta_t_deg=0.0,
                ),
            )
            with self.subTest(alpha_deg=alpha_deg):
                self.assertAlmostEqual(
                    integrated.total.CA,
                    2.0 * math.cos(alpha_rad) ** 2,
                    delta=1.0e-10,
                )
                self.assertEqual(0.0, integrated.total.CN)

    def test_modified_newtonian_uses_pinned_stagnation_cp(self) -> None:
        cp_max = modified_newtonian_cp_max(6.0, 1.4)
        loads = HypersonicModel().evaluate(
            _geometry(np.array([[-1.0, 0.0, 0.0]])),
            PanelFlowState(
                np.array([1.0, 0.0, 0.0]),
                np.array([False]),
            ),
            _case(windward_eq="modified_newtonian"),
        )
        self.assertGreater(cp_max, 0.0)
        self.assertLess(cp_max, 2.0)
        self.assertAlmostEqual(cp_max, loads.cell_scalars["cp"][0], places=12)

    def test_tangent_wedge_attached_and_detached_branches_are_retained(self) -> None:
        mach = 2.0
        gamma = 1.4
        cap = modified_newtonian_cp_max(mach, gamma)
        theta_max, cp_crit = _tangent_wedge_detach_limit(mach, gamma)
        theta = math.radians(40.0)
        cp = float(
            tangent_wedge_pressure_coefficient(
                mach,
                gamma,
                np.array([theta]),
                cp_cap=cap,
            )[0]
        )
        weight = (math.sin(theta) ** 2 - math.sin(theta_max) ** 2) / max(
            1.0 - math.sin(theta_max) ** 2,
            1.0e-12,
        )
        expected = cp_crit + (cap - cp_crit) * min(max(weight, 0.0), 1.0)
        self.assertGreater(theta, theta_max)
        self.assertAlmostEqual(expected, cp, places=12)

        attached = float(
            tangent_wedge_pressure_coefficient(
                6.0,
                1.4,
                np.array([math.radians(10.0)]),
                cp_cap=modified_newtonian_cp_max(6.0, 1.4),
            )[0]
        )
        self.assertGreater(attached, 0.0)

    def test_tangent_cone_taylor_maccoll_branch_and_detach_are_retained(self) -> None:
        mach = 6.0
        gamma = 1.4
        cap = modified_newtonian_cp_max(mach, gamma)
        attached = float(
            tangent_cone_pressure_coefficient(
                mach,
                gamma,
                np.array([math.radians(10.0)]),
                cp_cap=cap,
            )[0]
        )
        theta_max, cp_crit = _tangent_cone_detach_limit(mach, gamma)
        detached_angle = min(theta_max + math.radians(5.0), math.radians(85.0))
        detached = float(
            tangent_cone_pressure_coefficient(
                mach,
                gamma,
                np.array([detached_angle]),
                cp_cap=cap,
            )[0]
        )
        self.assertGreater(attached, 0.0)
        self.assertLess(attached, cap)
        self.assertGreater(detached, cp_crit)
        self.assertLess(detached, cap)

    def test_prandtl_meyer_iteration_and_vacuum_bound_are_retained(self) -> None:
        gamma = 1.67
        expected_mach = np.array([1.0571513513513513])
        estimated = _inverse_prandtl_meyer(
            _prandtl_meyer_nu(expected_mach, gamma),
            gamma,
        )
        self.assertAlmostEqual(estimated[0], expected_mach[0], places=9)

        cp = float(
            prandtl_meyer_pressure_coefficient(
                6.0,
                1.4,
                np.array([math.radians(-10.0)]),
            )[0]
        )
        self.assertLess(cp, 0.0)
        self.assertGreaterEqual(cp, -2.0 / (1.4 * 6.0 * 6.0))

    def test_component_overrides_stay_model_specific(self) -> None:
        geometry = _geometry(
            np.array([[-1.0, 0.0, 0.0], [-1.0, 0.0, 0.0]]),
            np.array([0, 1], dtype=np.int64),
        )
        loads = HypersonicModel().evaluate(
            geometry,
            PanelFlowState(
                np.array([1.0, 0.0, 0.0]),
                np.array([False, False]),
            ),
            _case(windward_eq="newtonian;modified_newtonian"),
        )
        self.assertEqual(2.0, loads.cell_scalars["cp"][0])
        self.assertAlmostEqual(
            modified_newtonian_cp_max(6.0, 1.4),
            loads.cell_scalars["cp"][1],
            places=12,
        )

        with self.assertRaises(HypersonicCaseError):
            HypersonicModel().evaluate(
                geometry,
                PanelFlowState(
                    np.array([1.0, 0.0, 0.0]),
                    np.array([False, False]),
                ),
                _case(windward_eq="newtonian;tangent_wedge;tangent_cone"),
            )

    def test_ray_shield_and_leeward_shield_remain_distinct(self) -> None:
        geometry = _geometry(np.array([[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0]]))
        flow = PanelFlowState(
            np.array([1.0, 0.0, 0.0]),
            np.array([True, False]),
        )
        loads = HypersonicModel().evaluate(geometry, flow, _case())
        np.testing.assert_array_equal(loads.traction_coeff_stl, np.zeros((2, 3)))
        np.testing.assert_array_equal(loads.cell_scalars["cp"], np.zeros(2))
        np.testing.assert_array_equal(
            loads.cell_scalars["theta_deg"],
            np.array([180.0, 0.0]),
        )

    def test_case_validation_normalizes_only_hypersonic_fields(self) -> None:
        model = HypersonicModel()
        case = _case(
            windward_eq=" TANGENT_CONE ; NEWTONIAN ",
            leeward_eq="PRANDTL_MEYER;SHIELD",
            unrelated="not-signed-by-model",
        )
        expected = {
            "Mach": 6.0,
            "gamma": 1.4,
            "windward_eq": "tangent_cone;newtonian",
            "leeward_eq": "prandtl_meyer;shield",
        }
        first = model.signature_payload(case)
        self.assertEqual(expected, first)
        first["Mach"] = 99.0
        self.assertEqual(expected, model.signature_payload(case))

        invalid = (
            _case(Mach=0.0),
            _case(gamma=1.0),
            _case(Mach=1.0, windward_eq="modified_newtonian"),
            _case(Mach=1.0, windward_eq="tangent_wedge"),
            _case(Mach=1.0, windward_eq="tangent_cone"),
            _case(Mach=1.0, leeward_eq="prandtl_meyer"),
            _case(windward_eq="shield"),
            _case(leeward_eq="newtonian_mirror"),
            _case(windward_eq="newtonian;;tangent_cone"),
        )
        for invalid_case in invalid:
            with (
                self.subTest(payload=dict(invalid_case.payload)),
                self.assertRaises(HypersonicCaseError),
            ):
                model.validate_case(invalid_case)

        model.validate_case(_case(Mach=0.5))


if __name__ == "__main__":
    unittest.main()
