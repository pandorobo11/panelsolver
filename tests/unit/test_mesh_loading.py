from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import PropertyMock, patch

import numpy as np
import trimesh

from panelsolver.core import (
    MeshLoadError,
    MeshValidationPolicy,
    clear_mesh_cache,
    geometry_fingerprint,
    load_panel_mesh,
    mesh_cache_stats,
)

FIXTURE_STL = Path(__file__).parents[1] / "fixtures" / "phase1" / "inputs" / "stl"


class MeshLoadingTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_mesh_cache()

    def test_loads_ordered_components_into_immutable_contract(self) -> None:
        loaded = load_panel_mesh(
            [FIXTURE_STL / "plate.stl", FIXTURE_STL / "plate_offset_x2.stl"],
            1.0,
        )

        self.assertEqual(4, loaded.mesh.n_faces)
        np.testing.assert_array_equal(loaded.mesh.face_component_ids, [0, 0, 1, 1])
        self.assertEqual(
            ["plate.stl", "plate_offset_x2.stl"],
            [Path(component.source).name for component in loaded.mesh.components],
        )
        self.assertFalse(loaded.mesh.vertices_stl_m.flags.writeable)
        self.assertFalse(loaded.mesh.geometry.normals_out_stl.flags.writeable)
        self.assertRegex(loaded.geometry_fingerprint, r"^[0-9a-f]{64}$")

    def test_cache_is_keyed_by_content_and_scale_with_policy_alias_normalized(
        self,
    ) -> None:
        path = FIXTURE_STL / "cube.stl"
        first = load_panel_mesh([path], 1.0)
        second = load_panel_mesh([path], 1.0)
        self.assertIs(first, second)
        stats = mesh_cache_stats()
        self.assertEqual((stats.entries, stats.hits, stats.misses), (1, 1, 1))

        scaled = load_panel_mesh([path], 0.5)
        permissive = load_panel_mesh(
            [path], 0.5, validation_policy=MeshValidationPolicy.LEGACY_WARN_REPAIR
        )
        self.assertNotEqual(first.geometry_fingerprint, scaled.geometry_fingerprint)
        self.assertEqual(scaled.geometry_fingerprint, permissive.geometry_fingerprint)
        self.assertIs(scaled, permissive)
        self.assertEqual(MeshValidationPolicy.STRICT, permissive.validation_policy)
        self.assertEqual(
            (1, 2, 2),
            (
                mesh_cache_stats().entries,
                mesh_cache_stats().hits,
                mesh_cache_stats().misses,
            ),
        )

    def test_cache_hit_replays_warnings_and_propagates_callback_errors(self) -> None:
        path = FIXTURE_STL / "plate.stl"
        first = load_panel_mesh([path], 1.0)
        self.assertTrue(first.warnings)
        stats = mesh_cache_stats()
        self.assertEqual((stats.entries, stats.hits, stats.misses), (1, 0, 1))

        observed: list[str] = []
        second = load_panel_mesh([path], 1.0, warning_callback=observed.append)
        self.assertIs(first, second)
        self.assertEqual(first.warnings, tuple(observed))
        self.assertEqual(first.geometry_fingerprint, second.geometry_fingerprint)
        stats = mesh_cache_stats()
        self.assertEqual((stats.entries, stats.hits, stats.misses), (1, 1, 1))

        failure = RuntimeError("warning callback failed")

        def fail_callback(_message: str) -> None:
            raise failure

        with self.assertRaises(RuntimeError) as caught:
            load_panel_mesh([path], 1.0, warning_callback=fail_callback)
        self.assertIs(failure, caught.exception)
        stats = mesh_cache_stats()
        self.assertEqual((stats.entries, stats.hits, stats.misses), (1, 2, 1))

    def test_cache_hit_warning_callback_can_reenter_mesh_cache(self) -> None:
        class FailOnReentryLock:
            def __init__(self) -> None:
                self.held = False

            def __enter__(self):
                if self.held:
                    raise RuntimeError("mesh cache lock was re-entered")
                self.held = True
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                self.held = False
                return False

        path = FIXTURE_STL / "plate.stl"
        first = load_panel_mesh([path], 1.0)
        reentrant: list[object] = []

        def callback(_message: str) -> None:
            reentrant.append(load_panel_mesh([path], 1.0))

        with patch("panelsolver.core.mesh_loading._CACHE_LOCK", FailOnReentryLock()):
            second = load_panel_mesh([path], 1.0, warning_callback=callback)

        self.assertIs(first, second)
        self.assertEqual([first], reentrant)
        stats = mesh_cache_stats()
        self.assertEqual((stats.entries, stats.hits, stats.misses), (1, 2, 1))

    def test_same_size_metadata_preserving_replacement_misses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "mesh.stl"
            first_mesh = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
            second_mesh = first_mesh.copy()
            second_mesh.apply_translation((0.25, 0.0, 0.0))
            original = first_mesh.export(file_type="stl")
            replacement = second_mesh.export(file_type="stl")
            self.assertIsInstance(original, bytes)
            self.assertIsInstance(replacement, bytes)
            self.assertEqual(len(original), len(replacement))
            path.write_bytes(original)
            original_stat = path.stat()
            first = load_panel_mesh([path], 1.0)

            path.write_bytes(replacement)
            os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            second = load_panel_mesh([path], 1.0)

        self.assertNotEqual(
            first.source_fingerprints[0].sha256,
            second.source_fingerprints[0].sha256,
        )
        self.assertEqual(mesh_cache_stats().misses, 2)

    def test_all_policy_names_reject_repair_failure(self) -> None:
        path = FIXTURE_STL / "cube.stl"
        for policy in MeshValidationPolicy:
            clear_mesh_cache()
            with (
                self.subTest(policy=policy),
                patch("trimesh.repair.fix_normals", side_effect=RuntimeError("repair")),
                self.assertRaisesRegex(MeshLoadError, "Failed to repair"),
            ):
                load_panel_mesh([path], 1.0, validation_policy=policy)

    def test_all_policy_names_reject_inconsistent_winding_after_repair(self) -> None:
        path = FIXTURE_STL / "cube.stl"
        for policy in MeshValidationPolicy:
            clear_mesh_cache()
            with (
                self.subTest(policy=policy),
                patch.object(
                    trimesh.Trimesh,
                    "is_winding_consistent",
                    new_callable=PropertyMock,
                    return_value=False,
                ),
                self.assertRaisesRegex(MeshLoadError, "winding remains inconsistent"),
            ):
                load_panel_mesh([path], 1.0, validation_policy=policy)

    def test_rejects_nonfinite_vertices_before_repair(self) -> None:
        mesh = trimesh.Trimesh(
            vertices=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]],
            faces=[[0, 1, 2]],
            process=False,
        )
        mesh.vertices[0, 0] = np.nan
        source = FIXTURE_STL / "cube.stl"
        with (
            patch("panelsolver.core.mesh_loading._load_source_mesh", return_value=mesh),
            patch("trimesh.repair.fix_normals") as repair,
        ):
            with self.assertRaisesRegex(MeshLoadError, "non-finite vertices"):
                load_panel_mesh([source], 1.0)
        repair.assert_not_called()

    def test_rejects_degenerate_nonfinite_and_invalid_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "degenerate.stl"
            trimesh.Trimesh(
                vertices=[[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
                faces=[[0, 1, 2]],
                process=False,
            ).export(path)
            for policy in MeshValidationPolicy:
                clear_mesh_cache()
                with self.subTest(policy=policy):
                    with self.assertRaisesRegex(MeshLoadError, "shared contract"):
                        load_panel_mesh([path], 1.0, validation_policy=policy)

        invalid_scales = (0.0, -1.0, float("nan"), float("inf"), True, "bad")
        for scale in invalid_scales:
            with self.subTest(scale=scale):
                with self.assertRaises(MeshLoadError):
                    load_panel_mesh([FIXTURE_STL / "cube.stl"], scale)
        with self.assertRaises(MeshLoadError):
            load_panel_mesh([], 1.0)
        with self.assertRaises(MeshLoadError):
            load_panel_mesh(str(FIXTURE_STL / "cube.stl"), 1.0)

    def test_fingerprint_is_content_based_and_field_sensitive(self) -> None:
        first = load_panel_mesh([FIXTURE_STL / "cube.stl"], 1.0)
        clear_mesh_cache()
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "renamed.stl"
            copied.write_bytes((FIXTURE_STL / "cube.stl").read_bytes())
            second = load_panel_mesh([copied], 1.0)

        self.assertEqual(first.geometry_fingerprint, second.geometry_fingerprint)
        self.assertEqual(first.geometry_fingerprint, geometry_fingerprint(first.mesh))
        self.assertNotEqual(
            first.geometry_fingerprint,
            load_panel_mesh([FIXTURE_STL / "cube.stl"], 2.0).geometry_fingerprint,
        )


if __name__ == "__main__":
    unittest.main()
