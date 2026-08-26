from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np
from trimesh.ray import has_embree

from panelsolver.core import (
    ShieldingConfig,
    clear_mesh_cache,
    clear_shielding_cache,
    compute_shielding,
    load_panel_mesh,
)

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "phase1"
GOLDEN_ROOT = FIXTURE_ROOT / "golden"


def _array(case: dict, name: str) -> np.ndarray:
    record = case["npz"]["arrays"][name]
    return np.asarray(record["values"]).reshape(record["shape"])


class ShieldingBackendGoldenTests(unittest.TestCase):
    def test_each_ray_backend_matches_the_legacy_mask(self) -> None:
        expected = np.array([False, False, True, True])
        for backend in ("rtree", "embree"):
            if backend == "embree" and not has_embree:
                self.skipTest("rayaccel extra is required for the Embree golden")
            case_path = GOLDEN_ROOT / "fmfsolver" / f"fmf_shield_{backend}.json"
            case = json.loads(case_path.read_text(encoding="utf-8"))
            clear_mesh_cache()
            clear_shielding_cache()
            loaded = load_panel_mesh(
                [FIXTURE_ROOT / "inputs" / "stl" / "double_plate.stl"],
                case["normalized_input"]["stl_scale_m_per_unit"],
            )
            result = compute_shielding(
                loaded.mesh,
                _array(case, "Vhat_stl"),
                ShieldingConfig(ray_backend=backend),
            )

            with self.subTest(backend=backend):
                np.testing.assert_array_equal(result.shielded, expected)
                np.testing.assert_array_equal(
                    result.shielded,
                    _array(case, "shielded").astype(bool),
                )
                self.assertEqual(backend, result.config.effective_backend)


if __name__ == "__main__":
    unittest.main()
