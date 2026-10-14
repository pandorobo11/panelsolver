from __future__ import annotations

from pathlib import Path

import numpy as np
import trimesh

from scripts.generate_sphere_cone_example import generate

ROOT = Path(__file__).resolve().parents[2]


def test_sphere_cone_generator_reproduces_shared_geometry_and_tables(tmp_path):
    generate(tmp_path)
    actual = trimesh.load_mesh(tmp_path / "geometry/sphere_cone.stl")
    expected = trimesh.load_mesh(ROOT / "examples/geometry/sphere_cone.stl")
    np.testing.assert_array_equal(actual.triangles, expected.triangles)
    assert len(actual.faces) == 9216
    assert actual.is_volume
    assert np.all(actual.area_faces > 0)
    np.testing.assert_allclose(actual.bounds[:, 1:], [[-0.5, -0.5], [0.5, 0.5]])
    for domain in ("fmf", "hypersonic"):
        relative = Path(domain) / "sphere_cone.csv"
        # Git may check out the reference CSVs with CRLF on Windows.
        assert (tmp_path / relative).read_text(encoding="utf-8") == (
            ROOT / "examples" / relative
        ).read_text(encoding="utf-8")
