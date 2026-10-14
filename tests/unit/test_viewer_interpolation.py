"""Exercise the actual VTK filters without creating a render window."""

import numpy as np
import pytest
import pyvista as pv

from panelsolver.app.viewer_interpolation import interpolated_surfaces


def two_triangles(*, separate_points=False, folded=False):
    points = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=float)
    faces = np.array([[0, 1, 2], [1, 3, 2]])
    if folded:
        points[3] = [0, 0, 1]
        faces[1] = [1, 0, 3]
    if separate_points:
        points = points[faces.ravel()]
        faces = np.arange(6).reshape(2, 3)
    mesh = pv.PolyData(points, np.column_stack([np.full(2, 3), faces]))
    mesh.cell_data["cp"] = [0.0, 1.0]
    return mesh


@pytest.mark.parametrize("separate_points", [False, True])
def test_shared_vertices_average_without_modifying_source(separate_points):
    mesh = two_triangles(separate_points=separate_points)
    mesh.cell_data["vector"] = np.ones((2, 3))
    mesh.point_data["cp"] = np.full(mesh.n_points, 99.0)
    mesh.field_data["case_id"] = ["source"]
    before = mesh.copy(deep=True)
    ((surface, masked),) = interpolated_surfaces(mesh, "cp")
    assert not masked
    assert surface.n_cells == 2
    np.testing.assert_array_equal(mesh.points, before.points)
    np.testing.assert_array_equal(mesh.faces, before.faces)
    for association in ("point_data", "cell_data", "field_data"):
        original, current = getattr(before, association), getattr(mesh, association)
        assert set(original) == set(current)
        for name in original:
            np.testing.assert_array_equal(original[name], current[name])
    assert set(surface.point_data) == {"cp"}
    assert set(surface.cell_data) == {"cp"}
    for point, value in zip(surface.points, surface.point_data["cp"], strict=True):
        expected = {(0, 0, 0): 0.0, (1, 0, 0): 0.5, (0, 1, 0): 0.5, (1, 1, 0): 1.0}
        assert value == expected[tuple(point)]
    # Filters may renumber vertices, but each panel's geometry/value must survive.
    for value in (0.0, 1.0):
        ids = np.flatnonzero(surface.cell_data["cp"] == value)
        original_ids = np.flatnonzero(mesh.cell_data["cp"] == value)
        np.testing.assert_array_equal(
            surface.cell_centers().points[ids], mesh.cell_centers().points[original_ids]
        )


@pytest.mark.parametrize("boundary", ["stl_index", "shielded"])
def test_component_and_shield_boundaries_do_not_average(boundary):
    mesh = two_triangles()
    mesh.cell_data[boundary] = [0, 1]
    surfaces = interpolated_surfaces(mesh, "cp")
    assert len(surfaces) == 2
    for surface, masked in surfaces:
        value = surface.cell_data["cp"][0]
        np.testing.assert_array_equal(surface.point_data["cp"], np.full(3, value))
        assert masked == (boundary == "shielded" and value == 1)


def test_sharp_edge_preserves_jump_and_flat_lighting():
    mesh = two_triangles(folded=True)
    ((surface, _),) = interpolated_surfaces(mesh, "cp")
    assert surface.n_points == 6
    assert set(surface.point_data["cp"]) == {0.0, 1.0}
    assert "Normals" not in surface.point_data


def test_integer_scalar_averages_in_floating_point():
    mesh = two_triangles()
    mesh.cell_data["count"] = np.array([0, 1], dtype=np.int32)
    ((surface, _),) = interpolated_surfaces(mesh, "count")
    assert 0.5 in surface.point_data["count"]


@pytest.mark.parametrize("name", ["shielded", "stl_index", "boolean"])
def test_categorical_arrays_are_not_interpolated(name):
    mesh = two_triangles()
    mesh.cell_data[name] = [False, True] if name == "boolean" else [0, 1]
    with pytest.raises(ValueError, match="continuous"):
        interpolated_surfaces(mesh, name)


def test_invalid_boundary_fails_instead_of_blending_components():
    mesh = two_triangles()
    mesh.cell_data["stl_index"] = [0, np.nan]
    with pytest.raises(ValueError, match="boundary"):
        interpolated_surfaces(mesh, "cp")
