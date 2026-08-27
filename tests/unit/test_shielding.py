from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np
from trimesh.ray import has_embree

from panelsolver.core import (
    MeshComponent,
    PanelGeometry,
    PanelMesh,
    RayBackend,
    ResolvedShieldingConfig,
    ShieldingConfig,
    ShieldingError,
    ShieldingResult,
    clear_mesh_cache,
    clear_shielding_cache,
    compute_shielding,
    load_panel_mesh,
    shielding_cache_stats,
    velocity_hat_stl_from_tangent_angles,
)

from .test_mesh_loading import FIXTURE_STL


class _CountingIntersector:
    def __init__(self) -> None:
        self.call_count = 0

    def intersects_id(self, **_kwargs):
        self.call_count += 1
        return np.array([], dtype=np.int64), np.array([], dtype=np.int64)


def _grazing_two_face_mesh() -> PanelMesh:
    # Amplify the 4e-13 direction delta into a robust 4e-7 m lateral shift.
    far_x_m = 1_000_000.0
    grazing_edge_y_m = -2.0e-7
    vertices = np.array(
        [
            [far_x_m, -1.0, -1.0],
            [far_x_m, 1.0, -1.0],
            [far_x_m, 0.0, 2.0],
            [0.0, grazing_edge_y_m, -1.0],
            [0.0, grazing_edge_y_m, 1.0],
            [0.0, -1.0, 0.0],
        ],
        dtype=np.float64,
    )
    faces = np.array([[0, 1, 2], [3, 4, 5]], dtype=np.int64)
    triangles = vertices[faces]
    cross = np.cross(
        triangles[:, 1] - triangles[:, 0],
        triangles[:, 2] - triangles[:, 0],
    )
    cross_norm = np.linalg.norm(cross, axis=1)
    return PanelMesh(
        vertices_stl_m=vertices,
        faces=faces,
        geometry=PanelGeometry(
            centers_stl_m=triangles.mean(axis=1),
            normals_out_stl=cross / cross_norm[:, None],
            areas_m2=0.5 * cross_norm,
            component_ids=np.zeros(2, dtype=np.int64),
        ),
        components=(MeshComponent(0, "synthetic-grazing-two-face"),),
    )


class ShieldingTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_mesh_cache()
        clear_shielding_cache()
        self.mesh = load_panel_mesh([FIXTURE_STL / "cube.stl"], 1.0).mesh

    def test_disabled_shielding_is_exact_zero_and_not_used(self) -> None:
        result = compute_shielding(
            self.mesh,
            np.array([1.0, 0.0, 0.0]),
            ShieldingConfig(enabled=False, ray_backend="embree"),
        )
        np.testing.assert_array_equal(result.shielded, np.zeros(12, dtype=bool))
        self.assertFalse(result.shielded.flags.writeable)
        self.assertEqual("embree", result.config.requested_backend)
        self.assertEqual("not_used", result.config.effective_backend)
        self.assertEqual(0, shielding_cache_stats().intersector_entries)

    def test_cache_key_includes_exact_direction_batch_backend_and_geometry(
        self,
    ) -> None:
        intersector = _CountingIntersector()
        other_mesh = load_panel_mesh([FIXTURE_STL / "plate.stl"], 1.0).mesh

        def resolve_intersector(_mesh, requested_backend, _fingerprint):
            return intersector, requested_backend.value

        with patch(
            "panelsolver.core.shielding._resolve_intersector",
            side_effect=resolve_intersector,
        ):
            first = compute_shielding(
                self.mesh,
                np.array([1.0, 0.0, 0.0]),
                ShieldingConfig(ray_backend="rtree", batch_size=8),
            )
            exact_repeat = compute_shielding(
                self.mesh,
                np.array([2.0, 0.0, 0.0]),
                ShieldingConfig(ray_backend="rtree", batch_size=8),
            )
            different_direction = compute_shielding(
                self.mesh,
                np.array([0.0, 1.0, 0.0]),
                ShieldingConfig(ray_backend="rtree", batch_size=8),
            )
            different_batch = compute_shielding(
                self.mesh,
                np.array([1.0, 0.0, 0.0]),
                ShieldingConfig(ray_backend="rtree", batch_size=3),
            )
            different_geometry = compute_shielding(
                other_mesh,
                np.array([1.0, 0.0, 0.0]),
                ShieldingConfig(ray_backend="rtree", batch_size=8),
            )
            different_backend = compute_shielding(
                self.mesh,
                np.array([1.0, 0.0, 0.0]),
                ShieldingConfig(ray_backend="embree", batch_size=8),
            )

        self.assertFalse(first.cache_hit)
        self.assertTrue(exact_repeat.cache_hit)
        for result in (
            different_direction,
            different_batch,
            different_geometry,
            different_backend,
        ):
            self.assertFalse(result.cache_hit)
        stats = shielding_cache_stats()
        self.assertEqual(
            (1, 1, 5),
            (stats.mask_entries, stats.mask_hits, stats.mask_misses),
        )

    def test_grazing_directions_have_distinct_real_rtree_masks_and_cache_keys(
        self,
    ) -> None:
        mesh = _grazing_two_face_mesh()
        direction_a = velocity_hat_stl_from_tangent_angles(0.0, 0.0)
        direction_b = velocity_hat_stl_from_tangent_angles(
            0.0,
            -2.291831180523293e-11,
        )
        uncached = ShieldingConfig(ray_backend="rtree", batch_size=2)
        cold_a = compute_shielding(mesh, direction_a, uncached)
        clear_shielding_cache()
        cold_b = compute_shielding(mesh, direction_b, uncached)
        np.testing.assert_array_equal(cold_a.shielded, [False, False])
        np.testing.assert_array_equal(cold_b.shielded, [True, False])
        self.assertEqual("rtree", cold_a.config.effective_backend)
        self.assertEqual("rtree", cold_b.config.effective_backend)

        clear_shielding_cache()
        cached = ShieldingConfig(ray_backend="rtree", batch_size=2)
        first_a = compute_shielding(mesh, direction_a, cached)
        first_b = compute_shielding(mesh, direction_b, cached)
        repeated_b = compute_shielding(mesh, direction_b, cached)

        np.testing.assert_array_equal(first_a.shielded, cold_a.shielded)
        np.testing.assert_array_equal(first_b.shielded, cold_b.shielded)
        np.testing.assert_array_equal(repeated_b.shielded, cold_b.shielded)
        self.assertFalse(first_a.cache_hit)
        self.assertFalse(first_b.cache_hit)
        self.assertTrue(repeated_b.cache_hit)
        stats = shielding_cache_stats()
        self.assertEqual(
            (1, 1, 2),
            (stats.mask_entries, stats.mask_hits, stats.mask_misses),
        )

    def test_cached_mask_cannot_be_mutated(self) -> None:
        first = compute_shielding(
            self.mesh,
            np.array([1.0, 0.0, 0.0]),
            ShieldingConfig(ray_backend="rtree"),
        )
        with self.assertRaises(ValueError):
            first.shielded[0] = not first.shielded[0]
        second = compute_shielding(
            self.mesh,
            np.array([1.0, 0.0, 0.0]),
            ShieldingConfig(ray_backend="rtree"),
        )
        np.testing.assert_array_equal(first.shielded, second.shielded)

    def test_explicit_unavailable_embree_does_not_fallback(self) -> None:
        with (
            patch("panelsolver.core.shielding.has_embree", False),
            patch("panelsolver.core.shielding._ray_pyembree", None),
        ):
            with self.assertRaisesRegex(ShieldingError, "not available"):
                compute_shielding(
                    self.mesh,
                    np.array([1.0, 0.0, 0.0]),
                    ShieldingConfig(ray_backend=RayBackend.EMBREE),
                )

    def test_auto_reports_the_effective_trimesh_backend(self) -> None:
        result = compute_shielding(
            self.mesh,
            np.array([1.0, 0.0, 0.0]),
            ShieldingConfig(ray_backend="auto"),
        )
        expected = "embree" if has_embree else "rtree"
        self.assertEqual("auto", result.config.requested_backend)
        self.assertEqual(expected, result.config.effective_backend)

    def test_rejects_invalid_direction_and_configuration(self) -> None:
        invalid_directions = (
            np.array([0.0, 0.0, 0.0]),
            np.array([1.0, 0.0]),
            np.array([np.nan, 0.0, 0.0]),
            np.array(["x", "y", "z"]),
        )
        for direction in invalid_directions:
            with self.subTest(direction=direction):
                with self.assertRaises(ShieldingError):
                    compute_shielding(self.mesh, direction)

        for kwargs in (
            {"batch_size": 0},
            {"ray_backend": "bad"},
            {"enabled": 1},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ShieldingError):
                    ShieldingConfig(**kwargs)

        with self.assertRaises(TypeError):
            ShieldingConfig(cache_max=1)

    def test_ragged_arrays_are_field_aware_shielding_errors(self) -> None:
        config = ResolvedShieldingConfig(
            enabled=False,
            requested_backend="auto",
            effective_backend="not_used",
            batch_size=0,
        )

        class TypeErrorArray:
            def __array__(self, *_args: object, **_kwargs: object) -> np.ndarray:
                raise TypeError("synthetic shielding coercion failure")

        cases = (
            (
                lambda: ShieldingResult(
                    [[True], [False, True]], config, "fingerprint", False
                ),
                "shielded",
                ValueError,
            ),
            (
                lambda: ShieldingResult(TypeErrorArray(), config, "fingerprint", False),
                "shielded",
                TypeError,
            ),
            (
                lambda: compute_shielding(
                    self.mesh,
                    [[1.0], [0.0, 0.0]],
                    ShieldingConfig(ray_backend="rtree"),
                ),
                "velocity_hat_stl",
                ValueError,
            ),
            (
                lambda: compute_shielding(
                    self.mesh,
                    TypeErrorArray(),
                    ShieldingConfig(ray_backend="rtree"),
                ),
                "velocity_hat_stl",
                TypeError,
            ),
        )
        for construct, field, cause_type in cases:
            with (
                self.subTest(field=field),
                self.assertRaisesRegex(ShieldingError, field) as caught,
            ):
                construct()
            self.assertIsInstance(caught.exception.__cause__, cause_type)

    def test_mask_and_intersector_caches_are_bounded_to_one_entry(self) -> None:
        other_mesh = load_panel_mesh([FIXTURE_STL / "plate.stl"], 1.0).mesh
        direction = np.array([1.0, 0.0, 0.0])
        compute_shielding(
            self.mesh,
            direction,
            ShieldingConfig(ray_backend="rtree"),
        )
        compute_shielding(
            other_mesh,
            direction,
            ShieldingConfig(ray_backend="rtree"),
        )
        stats = shielding_cache_stats()
        self.assertEqual(1, stats.mask_entries)
        self.assertEqual(1, stats.intersector_entries)


if __name__ == "__main__":
    unittest.main()
