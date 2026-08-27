from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from panelsolver.core import clear_mesh_cache, load_panel_mesh

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "phase1"
GOLDEN_ROOT = FIXTURE_ROOT / "golden"


def _array(case: dict, name: str) -> np.ndarray:
    record = case["npz"]["arrays"][name]
    return np.asarray(record["values"]).reshape(record["shape"])


class MeshLoadingGoldenTests(unittest.TestCase):
    def test_unique_legacy_mesh_configurations_keep_geometry_and_topology(
        self,
    ) -> None:
        # The 15 legacy cases collapse to these four unique combinations of
        # ordered STL content and scale. Model and ray-backend choices do not
        # participate in mesh loading.
        paths = (
            GOLDEN_ROOT / "fmfsolver" / "fmf_zero_plate.json",
            GOLDEN_ROOT / "fmfsolver" / "fmf_shield_rtree.json",
            GOLDEN_ROOT / "fmfsolver" / "fmf_bank_multicomponent.json",
            GOLDEN_ROOT / "newtsolver" / "newt_prandtl_meyer.json",
        )

        for path in paths:
            with self.subTest(solver=path.parent.name, case_id=path.stem):
                clear_mesh_cache()
                case = json.loads(path.read_text(encoding="utf-8"))
                normalized = case["normalized_input"]
                source_names = [
                    Path(value).name for value in str(normalized["stl_path"]).split(";")
                ]
                loaded = load_panel_mesh(
                    [FIXTURE_ROOT / "inputs" / "stl" / name for name in source_names],
                    normalized["stl_scale_m_per_unit"],
                )
                mesh = loaded.mesh

                np.testing.assert_allclose(
                    mesh.vertices_stl_m,
                    _array(case, "vertices"),
                    rtol=0.0,
                    atol=1.0e-12,
                )
                np.testing.assert_array_equal(mesh.faces, _array(case, "faces"))
                np.testing.assert_allclose(
                    mesh.geometry.centers_stl_m,
                    _array(case, "centers_stl_m"),
                    rtol=0.0,
                    atol=1.0e-12,
                )
                np.testing.assert_allclose(
                    mesh.geometry.normals_out_stl,
                    _array(case, "normals_out_stl"),
                    rtol=0.0,
                    atol=1.0e-12,
                )
                np.testing.assert_allclose(
                    mesh.geometry.areas_m2,
                    _array(case, "areas_m2"),
                    rtol=0.0,
                    atol=1.0e-12,
                )
                np.testing.assert_array_equal(
                    mesh.face_component_ids,
                    _array(case, "face_stl_index"),
                )


if __name__ == "__main__":
    unittest.main()
