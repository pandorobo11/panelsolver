"""Exercise the actual VTK filters without creating a render window."""

from unittest.mock import patch

import numpy as np
import pytest
import pyvista as pv

from panelsolver.app.viewer_data import (
    discover_scalar_fields,
    read_viewer_boundaries,
)
from panelsolver.app.viewer_interpolation import (
    interpolated_surfaces,
    prepare_interpolation_geometry,
)


def scalar(mesh, name):
    return next(
        field
        for field in discover_scalar_fields(mesh.cell_data, n_cells=mesh.n_cells)
        if field.name == name
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
    ((surface, masked),) = interpolated_surfaces(mesh, scalar(mesh, "cp"))
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
    surfaces = interpolated_surfaces(mesh, scalar(mesh, "cp"))
    assert len(surfaces) == (2 if boundary == "shielded" else 1)
    assert sum(surface.n_points for surface, _ in surfaces) == 6
    for surface, masked in surfaces:
        for cell_index in range(surface.n_cells):
            cell = surface.get_cell(cell_index)
            values = surface.point_data["cp"][cell.point_ids]
            # Each source triangle stays constant, even when its component is
            # appended into the same actor as a coincident neighbor.
            assert len(set(values)) == 1
            expected = float(np.any(np.all(cell.points == [1, 1, 0], axis=1)))
            np.testing.assert_array_equal(values, expected)
            assert masked == (boundary == "shielded" and expected == 1)


def test_sharp_edge_preserves_jump_and_flat_lighting():
    mesh = two_triangles(folded=True)
    ((surface, _),) = interpolated_surfaces(mesh, scalar(mesh, "cp"))
    assert surface.n_points == 6
    assert set(surface.point_data["cp"]) == {0.0, 1.0}
    assert "Normals" not in surface.point_data


def test_integer_scalar_averages_in_floating_point():
    mesh = two_triangles()
    mesh.cell_data["count"] = np.array([0, 1], dtype=np.int32)
    ((surface, _),) = interpolated_surfaces(mesh, scalar(mesh, "count"))
    assert 0.5 in surface.point_data["count"]


@pytest.mark.parametrize("name", ["shielded", "stl_index", "boolean"])
def test_categorical_arrays_are_not_interpolated(name):
    mesh = two_triangles()
    mesh.cell_data[name] = [False, True] if name == "boolean" else [0, 1]
    with pytest.raises(ValueError, match="continuous"):
        interpolated_surfaces(mesh, scalar(mesh, name))


def test_invalid_boundary_fails_instead_of_blending_components():
    mesh = two_triangles()
    mesh.cell_data["stl_index"] = [0, np.nan]
    with pytest.raises(ValueError, match="boundary"):
        interpolated_surfaces(mesh, scalar(mesh, "cp"))


def test_opposite_winding_coplanar_faces_stay_separate_and_preserve_source():
    mesh = two_triangles()
    mesh.faces = [3, 0, 1, 2, 3, 1, 2, 3]
    before = mesh.faces.copy()
    ((surface, _),) = interpolated_surfaces(mesh, scalar(mesh, "cp"))
    assert surface.n_points == 6
    assert set(surface.point_data["cp"]) == {0.0, 1.0}
    np.testing.assert_array_equal(mesh.faces, before)


def test_geometry_reuse_keeps_scalar_arrays_independent():
    from panelsolver.app.viewer_interpolation import prepare_interpolation_geometry

    mesh = two_triangles()
    mesh.cell_data["temperature"] = [10.0, 20.0]
    geometry = prepare_interpolation_geometry(mesh)
    ((first, _),) = interpolated_surfaces(mesh, scalar(mesh, "cp"), geometry)
    ((second, _),) = interpolated_surfaces(mesh, scalar(mesh, "temperature"), geometry)
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
    ((surface, _),) = interpolated_surfaces(mesh, scalar(mesh, "cp"))
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


@pytest.mark.parametrize("shielded", [False, True])
def test_many_components_append_without_averaging_across_components(shielded):
    parts = []
    for component in range(50):
        part = two_triangles()
        part.cell_data["stl_index"] = [component, component]
        part.cell_data["shielded"] = [0, int(shielded)]
        part.cell_data["cp"] = [2.0 * component, 2.0 * component + 1]
        parts.append(part)
    # All components coincide deliberately: appending must never merge points.
    mesh = parts[0].append_polydata(*parts[1:])
    geometry = prepare_interpolation_geometry(mesh)
    surfaces = interpolated_surfaces(mesh, scalar(mesh, "cp"), geometry)
    assert len(surfaces) == (2 if shielded else 1)
    assert sum(surface.n_cells for surface, _ in surfaces) == 100
    for item, (surface, masked) in zip(geometry, surfaces, strict=True):
        for cell_index, source_cell in enumerate(item.source_cells):
            values = surface.point_data["cp"][surface.get_cell(cell_index).point_ids]
            original = mesh.cell_data["cp"][source_cell]
            if shielded:
                np.testing.assert_array_equal(values, original)
            else:
                np.testing.assert_array_equal(
                    np.sort(values),
                    sorted(
                        [
                            original,
                            2 * (source_cell // 2) + 0.5,
                            2 * (source_cell // 2) + 0.5,
                        ]
                    ),
                )
            assert masked == bool(mesh.cell_data["shielded"][source_cell])


def test_nonzero_shield_values_share_one_interpolation_group():
    mesh = two_triangles()
    mesh.cell_data["shielded"] = [1, 2]
    ((surface, masked),) = interpolated_surfaces(mesh, scalar(mesh, "cp"))
    assert masked
    assert 0.5 in surface.point_data["cp"]


def test_direct_group_construction_supports_mixed_polygon_sizes():
    mesh = pv.PolyData(
        np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [2, 0, 0], [2, 1, 0]], dtype=float),
        [3, 0, 1, 2, 4, 1, 3, 4, 2],
    )
    mesh.cell_data["cp"] = [0.0, 1.0]
    with patch.object(
        pv.PolyData,
        "extract_cells",
        side_effect=AssertionError("whole-mesh extraction"),
    ):
        ((surface, _),) = interpolated_surfaces(mesh, scalar(mesh, "cp"))
    assert [surface.get_cell(i).n_points for i in range(2)] == [3, 4]
    np.testing.assert_array_equal(
        np.sort(surface.point_data["cp"]), [0, 0.5, 0.5, 1, 1]
    )


@pytest.mark.parametrize("folded", [False, True])
@pytest.mark.parametrize("association", ["point", "cell", "both"])
@pytest.mark.parametrize("separate_points", [False, True])
def test_imported_normals_are_preserved_without_affecting_averages(
    association, separate_points, folded
):
    mesh = two_triangles(separate_points=separate_points, folded=folded)
    if association in ("point", "both"):
        # Deliberately different shading normals at coincident corners.
        normals = np.array([[0, 0, 1], [0, 0.6, 0.8], [0.6, 0, 0.8]] * 2)[
            : mesh.n_points
        ]
        mesh.point_data["custom_normals"] = normals
        mesh.point_data.active_normals_name = "custom_normals"
    if association in ("cell", "both"):
        mesh.cell_data["cell_normals"] = np.array([[0, 0, 1], [0, 0.6, 0.8]])
        mesh.cell_data.active_normals_name = "cell_normals"
    before = mesh.copy(deep=True)
    ((surface, _),) = interpolated_surfaces(mesh, scalar(mesh, "cp"))
    for i in range(2):
        source_ids = mesh.get_cell(i).point_ids
        display_ids = surface.get_cell(i).point_ids
        if association in ("point", "both"):
            np.testing.assert_array_equal(
                surface.point_data.active_normals[display_ids],
                mesh.point_data.active_normals[source_ids],
            )
        if association in ("cell", "both"):
            np.testing.assert_array_equal(
                surface.cell_data.active_normals[i], mesh.cell_data.active_normals[i]
            )
    assert (0.5 in surface.point_data["cp"]) == (not folded)
    np.testing.assert_array_equal(mesh.faces, before.faces)
    for name in mesh.point_data:
        np.testing.assert_array_equal(mesh.point_data[name], before.point_data[name])
    for name in mesh.cell_data:
        np.testing.assert_array_equal(mesh.cell_data[name], before.cell_data[name])


def test_unreadable_shield_array_means_no_shielding_without_failing_load():
    class CellData(dict):
        def __getitem__(self, name):
            if name == "shielded":
                raise RuntimeError("unreadable VTK array")
            return super().__getitem__(name)

    cell_data = CellData(cp=np.array([0.0, 1.0]), shielded=None)
    fields = discover_scalar_fields({"cp": cell_data["cp"]}, n_cells=2)
    boundaries = read_viewer_boundaries(cell_data, n_cells=2, fields=fields)
    assert boundaries.shielded is None
    assert boundaries.error == "Invalid shielded boundary data"
