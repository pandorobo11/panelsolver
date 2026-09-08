from __future__ import annotations

import unittest

import numpy as np

from panelsolver.app.attitude import ResolvedAttitude, resolve_attitude


class ResolvedAttitudeInvariantTests(unittest.TestCase):
    def test_direct_construction_normalizes_and_freezes_finite_vectors(self) -> None:
        attitude = ResolvedAttitude(
            velocity_hat_stl=np.array([3.0, 4.0, 0.0]),
            alpha_deg="10.5",
            beta_or_bank_deg=-20,
            input_mode="BETA_TAN",
        )

        np.testing.assert_array_equal(attitude.velocity_hat_stl, [0.6, 0.8, 0.0])
        self.assertFalse(attitude.velocity_hat_stl.flags.writeable)
        self.assertIsInstance(attitude.velocity_hat_stl.base, bytes)
        self.assertEqual(10.5, attitude.alpha_deg)
        self.assertEqual(-20.0, attitude.beta_or_bank_deg)
        self.assertEqual("beta_tan", attitude.input_mode)

    def test_direct_construction_accepts_integer_vector(self) -> None:
        attitude = ResolvedAttitude([1, 0, 0], 0.0, 0.0, "beta_tan")

        np.testing.assert_array_equal(attitude.velocity_hat_stl, [1.0, 0.0, 0.0])
        self.assertEqual(np.dtype(np.float64), attitude.velocity_hat_stl.dtype)
        self.assertFalse(attitude.velocity_hat_stl.flags.writeable)
        self.assertIsInstance(attitude.velocity_hat_stl.base, bytes)

    def test_direct_construction_normalizes_extreme_finite_vectors(self) -> None:
        maximum = np.finfo(np.float64).max
        vectors = (
            [1.0e308, 1.0e308, 1.0e308],
            [1.2e308, 1.2e308, 1.2e308],
            [maximum, maximum, maximum],
            [maximum, 1.0, -maximum / 2.0],
        )
        for velocity in vectors:
            with self.subTest(velocity=velocity):
                attitude = ResolvedAttitude(
                    velocity_hat_stl=velocity,
                    alpha_deg=0.0,
                    beta_or_bank_deg=0.0,
                    input_mode="bank",
                )
                self.assertTrue(np.isfinite(attitude.velocity_hat_stl).all())
                self.assertAlmostEqual(
                    1.0,
                    float(np.linalg.norm(attitude.velocity_hat_stl)),
                    places=15,
                )
                self.assertFalse(attitude.velocity_hat_stl.flags.writeable)
                self.assertIsInstance(attitude.velocity_hat_stl.base, bytes)

        expected = np.full(3, 1.0 / np.sqrt(3.0))
        np.testing.assert_allclose(
            ResolvedAttitude(vectors[0], 0.0, 0.0, "bank").velocity_hat_stl,
            expected,
            rtol=0.0,
            atol=1.0e-15,
        )

    def test_direct_construction_rejects_invalid_angles(self) -> None:
        for field in ("alpha_deg", "beta_or_bank_deg"):
            for value in (True, np.bool_(False), np.nan, np.inf, -np.inf):
                kwargs = {
                    "velocity_hat_stl": [1.0, 0.0, 0.0],
                    "alpha_deg": 0.0,
                    "beta_or_bank_deg": 0.0,
                    "input_mode": "beta_tan",
                    field: value,
                }
                with (
                    self.subTest(field=field, value=value),
                    self.assertRaisesRegex(ValueError, field),
                ):
                    ResolvedAttitude(**kwargs)

    def test_direct_construction_rejects_invalid_vectors(self) -> None:
        invalid = (
            [True, False, False],
            np.array([True, False, False], dtype=np.bool_),
            np.array([1.0, 0.0, 0.0], dtype=np.complex128),
            np.array([1.0, 0.0, 0.0], dtype=object),
            np.array(["1", "0", "0"]),
            [[1.0], [0.0, 0.0]],
            [0.0, 0.0, 0.0],
            [1.0, 0.0],
            [np.nan, 0.0, 0.0],
            [np.inf, 0.0, 0.0],
        )
        for velocity in invalid:
            with (
                self.subTest(velocity=repr(velocity)),
                self.assertRaisesRegex(ValueError, "velocity_hat_stl"),
            ):
                ResolvedAttitude(velocity, 0.0, 0.0, "beta_tan")

    def test_resolve_attitude_rejects_boolean_angles_before_float_conversion(
        self,
    ) -> None:
        for alpha, beta in ((True, 0.0), (np.bool_(False), 0.0), (0.0, True)):
            with (
                self.subTest(alpha=alpha, beta=beta),
                self.assertRaisesRegex(ValueError, "finite real"),
            ):
                resolve_attitude(
                    alpha,
                    beta,
                    "beta_tan",
                )

    def test_sideslip_limits_and_tangent_singularities(self) -> None:
        for mode in ("beta_tan", "beta_sin"):
            for alpha in (-180, -100, -90, 0, 90, 100, 180, 460):
                for beta in (-90, -30, 0, 30, 90):
                    with self.subTest(mode=mode, alpha=alpha, beta=beta):
                        if mode == "beta_tan" and abs(alpha) == 90 and abs(beta) == 90:
                            with self.assertRaisesRegex(ValueError, "undefined"):
                                resolve_attitude(alpha, beta, mode)
                        else:
                            resolved = resolve_attitude(alpha, beta, mode)
                            self.assertTrue(
                                np.isfinite(resolved.velocity_hat_stl).all()
                            )
            for beta in (-91, 91, 360):
                with self.assertRaisesRegex(ValueError, "beta_or_bank_deg"):
                    resolve_attitude(0, beta, mode)
        for alpha in (-450, 270, 450):
            with self.assertRaisesRegex(ValueError, "undefined"):
                resolve_attitude(alpha, 90, "beta_tan")

    def test_exact_boundaries_and_adjacent_values(self) -> None:
        np.testing.assert_array_equal(
            resolve_attitude(90, 30, "beta_tan").velocity_hat_stl, [0, 0, 1]
        )
        for alpha in (np.nextafter(90.0, 0), np.nextafter(90.0, 180)):
            for beta in (np.nextafter(90.0, 0), 90):
                result = resolve_attitude(alpha, beta, "beta_tan")
                self.assertAlmostEqual(1, np.linalg.norm(result.velocity_hat_stl))
        for mode, alpha, beta in (
            ("beta_sin", 30, 90),
            ("beta_tan", 30, 90),
            ("bank", 90, 90),
        ):
            result = resolve_attitude(alpha, beta, mode)
            np.testing.assert_array_equal(result.velocity_hat_stl, [0, -1, 0])
            self.assertEqual(0, result.alpha_stability_deg)
            self.assertFalse(np.signbit(result.velocity_hat_stl[[0, 2]]).any())

    def test_backwards_sideslip_preserves_lateral_sign(self) -> None:
        expected = {
            "beta_sin": [-0.1503837331804353, -0.5, 0.8528685319524433],
            "beta_tan": [-0.17278201286621006, -0.099755741639431, 0.97989548832509],
        }
        for mode, vector in expected.items():
            result = resolve_attitude(100, 30, mode)
            np.testing.assert_allclose(
                result.velocity_hat_stl, vector, atol=1e-12, rtol=0
            )
            self.assertAlmostEqual(100, result.alpha_stability_deg)
            self.assertEqual(100, result.alpha_deg)
            self.assertEqual(30, result.beta_or_bank_deg)

    def test_original_angles_and_canonical_stability_angle(self) -> None:
        result = resolve_attitude(460, 30, "beta_sin")
        self.assertEqual(460, result.alpha_deg)
        self.assertAlmostEqual(100, result.alpha_stability_deg)
        for mode in ("beta_tan", "beta_sin", "bank"):
            self.assertEqual(-180, resolve_attitude(180, 0, mode).alpha_stability_deg)
            result = resolve_attitude(1e308, 0, mode)
            self.assertTrue(np.isfinite(result.velocity_hat_stl).all())

    def test_bank_accepts_finite_periodic_values(self) -> None:
        baseline = resolve_attitude(15.0, 30.0, "bank")
        for alpha, bank in ((375.0, 30.0), (15.0, 390.0), (-345.0, -330.0)):
            with self.subTest(alpha=alpha, bank=bank):
                periodic = resolve_attitude(alpha, bank, "BaNk")
                np.testing.assert_allclose(
                    baseline.velocity_hat_stl,
                    periodic.velocity_hat_stl,
                    rtol=0.0,
                    atol=1.0e-15,
                )

    def test_selector_accepts_only_none_or_text_without_truth_coercion(self) -> None:
        for selector in (None, "", "   ", "BETA_TAN", " beta_sin ", "BaNk"):
            with self.subTest(selector=repr(selector)):
                resolved = resolve_attitude(0.0, 0.0, selector)
                expected = (
                    "beta_tan"
                    if selector is None or not selector.strip()
                    else (selector.strip().lower())
                )
                self.assertEqual(expected, resolved.input_mode)

        for selector in (False, 0, [], object()):
            with (
                self.subTest(selector=repr(selector)),
                self.assertRaisesRegex(
                    TypeError, "attitude_input must be text or None"
                ),
            ):
                resolve_attitude(0.0, 0.0, selector)
        with self.assertRaisesRegex(ValueError, "Invalid attitude_input"):
            resolve_attitude(0.0, 0.0, "unknown")


if __name__ == "__main__":
    unittest.main()
