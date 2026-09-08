import unittest

import numpy as np

from panelsolver.core import (
    ContractValueError,
    NonFiniteError,
    ShapeError,
    body_to_stability,
    stability_alpha_deg,
    stl_to_body,
)


class ResolvedAttitudeTests(unittest.TestCase):
    def test_axes_and_backwards_flow(self) -> None:
        for vector, angle in (
            ([1, 0, 0], 0),
            ([0, 0, 1], 90),
            ([0, 0, -1], -90),
            ([-1, 0, 0], -180),
            ([0, 1, 0], 0),
            ([0, -1, 0], 0),
        ):
            with self.subTest(vector=vector):
                self.assertEqual(angle, stability_alpha_deg(vector))

    def test_fallback_threshold_does_not_modify_direction(self) -> None:
        threshold = 64 * np.finfo(np.float64).eps
        for radius, expected in (
            (threshold / 2, 0),
            (threshold, 0),
            (threshold * 2, 90),
        ):
            vector = np.array([0.0, 1.0, radius])
            original = vector.copy()
            self.assertEqual(expected, stability_alpha_deg(vector))
            np.testing.assert_array_equal(vector, original)

    def test_invalid_directions_are_rejected(self) -> None:
        for vector in ([0, 0, 0], [2, 0, 0], [True, False, False]):
            with self.assertRaises(ContractValueError):
                stability_alpha_deg(vector)
        with self.assertRaises(NonFiniteError):
            stability_alpha_deg([np.nan, 0, 0])


class FrameTransformTests(unittest.TestCase):
    def test_stl_to_body_preserves_arbitrary_leading_dimensions(self) -> None:
        vectors_stl = np.arange(24, dtype=np.float32).reshape(2, 4, 3)
        original = vectors_stl.copy()

        vectors_body = stl_to_body(vectors_stl)

        np.testing.assert_array_equal(
            vectors_body,
            original * np.array([-1.0, 1.0, -1.0]),
        )
        np.testing.assert_array_equal(vectors_stl, original)
        self.assertEqual(vectors_stl.shape, vectors_body.shape)
        self.assertEqual(np.dtype(np.float64), vectors_body.dtype)
        self.assertTrue(vectors_body.flags.c_contiguous)

    def test_stl_to_body_is_its_own_inverse(self) -> None:
        vectors = np.array([[1.0, 2.0, 3.0], [-4.0, 5.0, -6.0]])
        np.testing.assert_array_equal(vectors, stl_to_body(stl_to_body(vectors)))

    def test_body_to_stability_uses_positive_y_rotation(self) -> None:
        transformed = body_to_stability(
            np.array([1.0, 2.0, 3.0]),
            alpha_stability_deg=90.0,
        )
        np.testing.assert_allclose(
            np.array([3.0, 2.0, -1.0]),
            transformed,
            rtol=0.0,
            atol=1.0e-15,
        )

    def test_vector_transforms_reject_invalid_shape_dtype_and_values(self) -> None:
        for value in (1.0, [1.0, 2.0], np.zeros((2, 3, 4))):
            with self.subTest(value=np.shape(value)):
                with self.assertRaises(ShapeError):
                    stl_to_body(value)
        with self.assertRaises(ContractValueError):
            stl_to_body([True, False, True])
        with self.assertRaises(ContractValueError):
            body_to_stability(["1", "2", "3"], alpha_stability_deg=0.0)
        with self.assertRaises(ContractValueError):
            stl_to_body([[1.0, 2.0, 3.0], [4.0, 5.0]])
        with self.assertRaises(NonFiniteError):
            body_to_stability([1.0, np.nan, 3.0], alpha_stability_deg=0.0)


if __name__ == "__main__":
    unittest.main()
