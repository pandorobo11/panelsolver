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
    _tangent_wedge_detach_limit,
    modified_newtonian_cp_max,
    prandtl_meyer_pressure_coefficient,
    tangent_wedge_pressure_coefficient,
)
from panelsolver.models.hypersonic.tangent_wedge import _weak_oblique_shock_beta


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


def _cot_beta_cubic(mach: float, gamma: float, theta_rad: float) -> np.ndarray:
    """Coefficients of the theta-beta-Mach relation as a cubic in cot(beta)."""
    tan_theta = math.tan(theta_rad)
    m2 = mach * mach
    return np.array(
        [
            2.0,
            tan_theta * (m2 * (gamma + 1.0) + 2.0),
            -2.0 * (m2 - 1.0),
            tan_theta * (m2 * (gamma - 1.0) + 2.0),
        ]
    )


def _depressed_cubic_discriminant(coefficients: np.ndarray) -> float:
    """Cardano discriminant ``(q/2)^2 + (p/3)^3`` of a monic-normalized cubic."""
    ba, ca, da = coefficients[1:] / coefficients[0]
    p = ca - ba * ba / 3.0
    q = 2.0 * ba**3 / 27.0 - ba * ca / 3.0 + da
    return float((0.5 * q) ** 2 + (p / 3.0) ** 3)


def _theta_from_beta(mach: float, gamma: float, beta_rad: float) -> float:
    """Oblique-shock theta-beta-Mach relation (Anderson, Modern Compressible Flow)."""
    m2 = mach * mach
    return math.atan(
        2.0
        / math.tan(beta_rad)
        * (m2 * math.sin(beta_rad) ** 2 - 1.0)
        / (m2 * (gamma + math.cos(2.0 * beta_rad)) + 2.0)
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
                    alpha_stability_deg=alpha_deg,
                ),
            )
            with self.subTest(alpha_deg=alpha_deg):
                self.assertAlmostEqual(
                    integrated.total.CA,
                    2.0 * math.cos(alpha_rad) ** 2,
                    delta=1.0e-10,
                )
                self.assertEqual(0.0, integrated.total.CN)

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
        # Independent evaluation of the documented continuation in
        # docs/methods/hypersonic.md#detached-branch-continuation.
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

    def test_weak_shock_cubic_single_and_three_real_root_branches(self) -> None:
        mach = 2.0
        gamma = 1.4
        theta_max, _cp_crit = _tangent_wedge_detach_limit(mach, gamma)
        theta_attached = 0.2
        theta_detached = theta_max + 0.05
        coefficients = {
            theta: _cot_beta_cubic(mach, gamma, theta)
            for theta in (theta_attached, theta_detached)
        }
        # Guard that the chosen inputs reach the intended Cardano branches.
        self.assertLess(
            _depressed_cubic_discriminant(coefficients[theta_attached]), -1.0e-3
        )
        self.assertGreater(
            _depressed_cubic_discriminant(coefficients[theta_detached]), 1.0e-3
        )

        beta = _weak_oblique_shock_beta(
            mach, gamma, np.array([theta_attached, theta_detached])
        )

        # Attached: three real roots; the weak shock is the largest admissible
        # cot(beta), i.e. the smallest shock angle above the Mach angle.
        roots = np.roots(coefficients[theta_attached])
        self.assertTrue(np.all(np.abs(roots.imag) < 1.0e-12))
        admissible = roots.real[
            (roots.real > 0.0) & (roots.real < math.sqrt(mach * mach - 1.0))
        ]
        self.assertEqual(2, admissible.size)
        expected_beta = math.atan2(1.0, float(np.max(admissible)))
        self.assertAlmostEqual(expected_beta, beta[0], places=12)
        self.assertGreater(beta[0], math.asin(1.0 / mach))
        self.assertAlmostEqual(
            theta_attached, _theta_from_beta(mach, gamma, beta[0]), places=12
        )

        # Detached: one real root and it is negative, so no attached solution.
        roots = np.roots(coefficients[theta_detached])
        real_roots = roots.real[np.abs(roots.imag) < 1.0e-9]
        self.assertEqual(1, real_roots.size)
        self.assertLess(real_roots[0], 0.0)
        self.assertTrue(np.isnan(beta[1]))

    def test_weak_shock_cubic_double_root_at_detachment(self) -> None:
        mach = 1.01
        gamma = 1.4
        theta_max, cp_crit = _tangent_wedge_detach_limit(mach, gamma)
        coefficients = _cot_beta_cubic(mach, gamma, theta_max)
        # At the detachment angle weak and strong roots coincide; the
        # discriminant is within the solver's near-zero tolerance.
        self.assertLessEqual(abs(_depressed_cubic_discriminant(coefficients)), 1e-16)

        m2 = mach * mach
        term_a = (gamma + 1.0) * m2 / 4.0 - 1.0
        term_b = (gamma + 1.0) * (
            (gamma + 1.0) * m2 * m2 / 16.0 + (gamma - 1.0) * m2 / 2.0 + 1.0
        )
        beta_max = math.asin(math.sqrt((term_a + math.sqrt(term_b)) / (gamma * m2)))
        positive = np.sort(np.roots(coefficients).real)[1:]
        self.assertAlmostEqual(positive[0], positive[1], places=6)
        self.assertAlmostEqual(math.atan2(1.0, float(positive.mean())), beta_max, 9)

        beta = float(_weak_oblique_shock_beta(mach, gamma, np.array([theta_max]))[0])
        self.assertAlmostEqual(beta_max, beta, places=12)
        self.assertAlmostEqual(theta_max, _theta_from_beta(mach, gamma, beta), 12)

        cap = modified_newtonian_cp_max(mach, gamma)
        cp = tangent_wedge_pressure_coefficient(
            mach, gamma, np.array([theta_max]), cp_cap=cap
        )[0]
        mn1_sq = m2 * math.sin(beta_max) ** 2
        expected_cp = 4.0 * (mn1_sq - 1.0) / ((gamma + 1.0) * m2)
        self.assertAlmostEqual(expected_cp, cp, places=10)
        self.assertAlmostEqual(cp_crit, cp, places=10)

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
