"""Exercise the actual VTK filters without creating a render window."""

from unittest.mock import patch

import numpy as np
import pytest
import pyvista as pv

from panelsolver.app.viewer_interpolation import (
    interpolated_surfaces,
    prepare_interpolation_geometry,
)


def test_cleaning_cannot_silently_drop_degenerate_source_cells():
    mesh = pv.PolyData(
        np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 0, 0]], dtype=float),
        [3, 0, 1, 2, 3, 0, 1, 3],
    )
    mesh.cell_data["cp"] = [0.0, 1.0]
    before = mesh.copy(deep=True)
    with pytest.raises(ValueError, match="every source cell"):
        prepare_interpolation_geometry(mesh)
    np.testing.assert_array_equal(mesh.points, before.points)
    np.testing.assert_array_equal(mesh.faces, before.faces)
    np.testing.assert_array_equal(mesh.cell_data["cp"], before.cell_data["cp"])


@pytest.mark.parametrize("multiple_groups", [False, True])
def test_column_shaped_unique_inverse_preserves_all_cells(multiple_groups):
    mesh = two_triangles()
    mesh.cell_data["stl_index"] = [0, int(multiple_groups)]
    unique = np.unique

    def numpy_200_unique(*args, **kwargs):
        result = unique(*args, **kwargs)
        if kwargs.get("axis") == 0 and kwargs.get("return_inverse"):
            keys, inverse = result
            return keys, inverse.reshape(-1, 1)
        return result

    with patch(
        "panelsolver.app.viewer_interpolation.np.unique", side_effect=numpy_200_unique
    ):
        geometry = prepare_interpolation_geometry(mesh)
    assert sum(item.surface.n_cells for item in geometry) == mesh.n_cells
    np.testing.assert_array_equal(
        np.sort(np.concatenate([item.source_cells for item in geometry])), [0, 1]
    )


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
    assert not surface.cell_data
    for point, value in zip(surface.points, surface.point_data["cp"], strict=True):
        expected = {(0, 0, 0): 0.0, (1, 0, 0): 0.5, (0, 1, 0): 0.5, (1, 1, 0): 1.0}
        assert value == expected[tuple(point)]


@pytest.mark.parametrize("boundary", ["stl_index", "shielded"])
def test_component_and_shield_boundaries_do_not_average(boundary):
    mesh = two_triangles()
    mesh.cell_data[boundary] = [0, 1]
    surfaces = interpolated_surfaces(mesh, "cp")
    assert len(surfaces) == 2
    for value, (surface, masked) in enumerate(surfaces):
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


def test_opposite_winding_coplanar_faces_stay_separate_and_preserve_source():
    mesh = two_triangles()
    mesh.faces = [3, 0, 1, 2, 3, 1, 2, 3]
    before = mesh.faces.copy()
    ((surface, _),) = interpolated_surfaces(mesh, "cp")
    assert surface.n_points == 6
    assert set(surface.point_data["cp"]) == {0.0, 1.0}
    np.testing.assert_array_equal(mesh.faces, before)


def test_geometry_reuse_keeps_scalar_arrays_independent():
    from panelsolver.app.viewer_interpolation import prepare_interpolation_geometry

    mesh = two_triangles()
    mesh.cell_data["temperature"] = [10.0, 20.0]
    geometry = prepare_interpolation_geometry(mesh)
    ((first, _),) = interpolated_surfaces(mesh, "cp", geometry)
    ((second, _),) = interpolated_surfaces(mesh, "temperature", geometry)
    assert 0.5 in first.point_data["cp"]
    assert 15.0 in second.point_data["temperature"]
    assert not first.cell_data and not second.cell_data
    assert not geometry[0].surface.cell_data


@pytest.mark.parametrize("angle_deg", [0, 15, 29.9, 30.1, 90, 150, 180])
@pytest.mark.parametrize("reverse", [False, True])
def test_split_uses_original_normal_angle(angle_deg, reverse):
    angle = np.deg2rad(angle_deg)
    points = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, -np.cos(angle), np.sin(angle)]],
        dtype=float,
    )
    faces = np.array([[0, 1, 2], [0, 1, 3] if reverse else [1, 0, 3]])
    mesh = pv.PolyData(points, np.column_stack([np.full(2, 3), faces]))
    mesh.cell_data["cp"] = [0.0, 1.0]
    original_faces = mesh.faces.copy()
    ((surface, _),) = interpolated_surfaces(mesh, "cp")
    normal_angle = 180 - angle_deg if reverse else angle_deg
    edge = np.isclose(surface.points[:, 1], 0, atol=1e-12) & np.isclose(
        surface.points[:, 2], 0, atol=1e-12
    )
    if normal_angle < 30:
        np.testing.assert_array_equal(surface.point_data["cp"][edge], 0.5)
    else:
        assert set(surface.point_data["cp"][edge]) == {0.0, 1.0}
    np.testing.assert_array_equal(mesh.faces, original_faces)
    np.testing.assert_array_equal(mesh.cell_data["cp"], [0.0, 1.0])
