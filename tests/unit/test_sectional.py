"""A1 numerical input boundary tests; no physical solves or clipping."""

from __future__ import annotations

import pickle
import warnings
from dataclasses import FrozenInstanceError

import numpy as np
import pytest

from panelsolver.core import (
    ContractError,
    ContractValueError,
    MeshComponent,
    NonFiniteError,
    PanelGeometry,
    PanelMesh,
    ShapeError,
)
from panelsolver.core.sectional import (
    ResolvedSectionalLoadSpec,
    SectionalLoadDefinition,
    resolve_sectional_load_spec,
)


def definition(**changes: object) -> SectionalLoadDefinition:
    inputs = {
        "axis_origin_stl_m": (0.0, 0.0, 0.0),
        "axis_direction_stl": (1.0, 0.0, 0.0),
        "bin_count": 4,
    }
    inputs.update(changes)
    return SectionalLoadDefinition(**inputs)


def make_mesh(vertices=None, faces=None, ids=None) -> PanelMesh:
    # Components 2 and 7 share vertices 1 and 2. Vertex 7 is unused and must
    # never affect any projection, even for an all-components selection.
    vertices = np.array(
        vertices
        if vertices is not None
        else [
            [0, 0, 0],
            [2, 0, 0],
            [0, 2, 0],
            [6, 2, 0],
            [-4, 0, 0],
            [-2, 0, 0],
            [-4, 2, 0],
            [1.0e300, -1.0e300, 1.0e300],
        ],
        dtype=np.float64,
    )
    faces = np.array(faces if faces is not None else [[1, 3, 2], [4, 5, 6], [0, 1, 2]])
    ids = np.array(ids if ids is not None else [7, 11, 2], dtype=np.int64)
    triangles = vertices[faces]
    crosses = np.cross(
        triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]
    )
    twice_areas = np.linalg.norm(crosses, axis=1)
    centers = (
        triangles[:, 0]
        + ((triangles[:, 1] - triangles[:, 0]) + (triangles[:, 2] - triangles[:, 0]))
        / 3
    )
    geometry = PanelGeometry(
        centers, crosses / twice_areas[:, None], twice_areas / 2, ids
    )
    return PanelMesh(
        vertices,
        faces,
        geometry,
        tuple(
            MeshComponent(int(component), f"component-{component}.stl")
            for component in np.unique(ids)
        ),
    )


@pytest.fixture
def mesh() -> PanelMesh:
    return make_mesh()


@pytest.mark.parametrize(
    "direction, expected",
    [
        ((2, -3, 6), np.array([2, -3, 6]) / 7),
        ((0, 20, 0), [0, 1, 0]),
        ((-2, 3, -6), np.array([-2, 3, -6]) / 7),
        ((-20, 0, 0), [-1, 0, 0]),
    ],
)
def test_direction_normalizes_without_changing_sign(mesh, direction, expected):
    item = definition(axis_direction_stl=direction, start_m=-1, stop_m=1)
    spec = resolve_sectional_load_spec(mesh, item)
    np.testing.assert_array_equal(item.axis_direction_stl, direction)
    np.testing.assert_allclose(
        spec.axis_direction_hat_stl, expected, rtol=0, atol=2e-16
    )
    assert np.linalg.norm(spec.axis_direction_hat_stl) == pytest.approx(
        1, rel=0, abs=1e-15
    )


@pytest.mark.parametrize(
    "scale", [np.finfo(float).max, 1e-300, np.finfo(float).smallest_subnormal]
)
def test_extreme_finite_directions_are_safe(mesh, scale):
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        item = definition(axis_direction_stl=(scale, -scale, scale))
        spec = resolve_sectional_load_spec(mesh, item)
    np.testing.assert_allclose(
        spec.axis_direction_hat_stl,
        np.array([1, -1, 1]) / np.sqrt(3),
        rtol=0,
        atol=2e-16,
    )
    assert np.linalg.norm(spec.axis_direction_hat_stl) == pytest.approx(
        1, rel=0, abs=1e-15
    )


def test_direction_with_extreme_dynamic_range(mesh):
    item = definition(
        axis_direction_stl=(np.finfo(float).max, np.finfo(float).smallest_subnormal, 0)
    )
    np.testing.assert_array_equal(
        resolve_sectional_load_spec(mesh, item).axis_direction_hat_stl, [1, 0, 0]
    )


@pytest.mark.parametrize("field", ["axis_origin_stl_m", "axis_direction_stl"])
@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf, 10**400])
def test_axis_rejects_nonfinite_float64_values(field, value):
    with pytest.raises(NonFiniteError):
        definition(**{field: [value, 0, 1]})


@pytest.mark.parametrize("field", ["axis_origin_stl_m", "axis_direction_stl"])
@pytest.mark.parametrize("value", [True, np.bool_(False), "1", 1j, None])
def test_axis_rejects_nonreal_and_mixed_boolean_values(field, value):
    with pytest.raises(ContractValueError):
        definition(**{field: [value, 0, 1]})


@pytest.mark.parametrize("field", ["axis_origin_stl_m", "axis_direction_stl"])
@pytest.mark.parametrize(
    "value", [1, [], [1, 2], [1, 2, 3, 4], [[1, 2, 3]], [[1], [2], [3]]]
)
def test_axis_shape_is_checked_before_broadcasting(field, value):
    with pytest.raises(ShapeError):
        definition(**{field: value})


def test_ragged_axis_and_zero_direction_are_rejected():
    with pytest.raises(ContractError):
        definition(axis_direction_stl=[[1, 2], [3], [4]])
    with pytest.raises(ContractValueError):
        definition(axis_direction_stl=[0, -0.0, 0])


@pytest.mark.parametrize("bounds", [(None, None), (1, 3), (-4, -1), (-2, 3)])
def test_range_inputs_and_mode(mesh, bounds):
    item = definition(start_m=bounds[0], stop_m=bounds[1])
    spec = resolve_sectional_load_spec(mesh, item)
    assert (spec.definition.start_m, spec.definition.stop_m) == bounds
    assert spec.range_mode == ("auto" if bounds[0] is None else "explicit")
    assert (spec.resolved_start_m, spec.resolved_stop_m) == (
        (-4, 6) if bounds[0] is None else bounds
    )


@pytest.mark.parametrize("bounds", [(None, 1), (0, None), (1, 1), (2, -1)])
def test_incomplete_equal_or_reversed_bounds_are_rejected(bounds):
    with pytest.raises(ContractValueError):
        definition(start_m=bounds[0], stop_m=bounds[1])


@pytest.mark.parametrize("field", ["start_m", "stop_m"])
@pytest.mark.parametrize(
    "value", [np.nan, np.inf, -np.inf, True, np.bool_(False), "1", 1j, [1], 10**400]
)
def test_range_rejects_invalid_scalars(field, value):
    inputs = {"start_m": -1, "stop_m": 1}
    inputs[field] = value
    with pytest.raises(ContractError):
        definition(**inputs)


@pytest.mark.parametrize(
    "requested, ids, faces, all_selected",
    [
        (None, (2, 7, 11), [0, 1, 2], True),
        ((2,), (2,), [2], False),
        ((7, 2), (2, 7), [0, 2], False),
        ((11, 7, 2), (2, 7, 11), [0, 1, 2], True),
        (np.array([11, 2], dtype=np.int32), (2, 11), [1, 2], False),
    ],
)
def test_component_selection_is_sparse_sorted_and_face_based(
    mesh, requested, ids, faces, all_selected
):
    spec = resolve_sectional_load_spec(mesh, definition(component_ids=requested))
    assert spec.selected_component_ids == ids
    assert spec.all_components_selected is all_selected
    np.testing.assert_array_equal(spec.selected_face_indices, faces)
    assert spec.selected_face_indices.dtype == np.int64


@pytest.mark.parametrize(
    "ids",
    [
        (),
        (2, 2),
        (-1,),
        (True,),
        (2, False),
        (np.bool_(True),),
        (2.0,),
        ("2",),
        (2**63,),
        (10**100,),
        [[2]],
        2,
        "2",
    ],
)
def test_component_input_errors(ids):
    with pytest.raises(ContractError):
        definition(component_ids=ids)


@pytest.mark.parametrize("ids", [(0,), (2, 3), (2, 7, 11, 99)])
def test_unknown_ids_are_rejected_not_skipped(mesh, ids):
    item = definition(component_ids=ids)
    with pytest.raises(ContractValueError):
        resolve_sectional_load_spec(mesh, item)


def test_maximum_int64_component_id_is_supported():
    maximum = np.iinfo(np.int64).max
    mesh = make_mesh([[0, 0, 0], [2, 0, 0], [0, 2, 0]], [[0, 1, 2]], [maximum])
    spec = resolve_sectional_load_spec(mesh, definition(component_ids=(maximum,)))
    assert spec.selected_component_ids == (maximum,)
    assert spec.all_components_selected


def test_multiple_faces_per_component_and_widely_separated_sparse_ids():
    largest_id = np.iinfo(np.int64).max
    mesh = make_mesh(ids=[largest_id, 0, largest_id])
    spec = resolve_sectional_load_spec(mesh, definition(component_ids=(largest_id,)))
    assert spec.selected_component_ids == (largest_id,)
    np.testing.assert_array_equal(spec.selected_face_indices, [0, 2])
    assert (spec.selected_geometry_min_m, spec.selected_geometry_max_m) == (0, 6)
    assert not spec.all_components_selected


@pytest.mark.parametrize(
    "ids, bounds",
    [
        (None, (-4, 6)),
        ((2,), (0, 2)),
        ((7,), (0, 6)),
        ((11,), (-4, -2)),
        ((11, 2), (-4, 2)),
    ],
)
def test_auto_range_uses_only_selected_referenced_vertices(mesh, ids, bounds):
    # This has no load or shielding inputs: all selected faces determine range.
    spec = resolve_sectional_load_spec(mesh, definition(component_ids=ids))
    assert (spec.resolved_start_m, spec.resolved_stop_m) == bounds
    assert (spec.selected_geometry_min_m, spec.selected_geometry_max_m) == bounds
    assert spec.covers_selected_geometry
    assert (
        spec.bin_edges_m[[0, -1]].tobytes()
        == np.array(bounds, dtype=np.float64).tobytes()
    )
    # At least one geometry bound differs from the range of face centers.
    centers = mesh.geometry.centers_stl_m[spec.selected_face_indices, 0]
    assert (float(centers.min()), float(centers.max())) != bounds


def test_oblique_projection_uses_origin_and_shared_vertices(mesh):
    item = definition(
        axis_origin_stl_m=(1, -2, 3), axis_direction_stl=(2, -3, 6), component_ids=(2,)
    )
    spec = resolve_sectional_load_spec(mesh, item)
    # Analytic projections of the three vertices: -26/7, -22/7, -32/7.
    np.testing.assert_allclose(
        [spec.selected_geometry_min_m, spec.selected_geometry_max_m],
        [-32 / 7, -22 / 7],
        rtol=0,
        atol=1e-15,
    )


def test_reversing_axis_reverses_geometry_and_auto_edges(mesh):
    forward = resolve_sectional_load_spec(mesh, definition(component_ids=(7,)))
    reverse = resolve_sectional_load_spec(
        mesh, definition(axis_direction_stl=(-4, 0, 0), component_ids=(7,))
    )
    assert (reverse.selected_geometry_min_m, reverse.selected_geometry_max_m) == (-6, 0)
    np.testing.assert_array_equal(reverse.bin_edges_m, -forward.bin_edges_m[::-1])


def test_zero_extent_rejects_auto_but_accepts_explicit_bounds(mesh):
    item = definition(axis_direction_stl=(0, 0, 2))
    with pytest.raises(ContractValueError):
        resolve_sectional_load_spec(mesh, item)
    spec = resolve_sectional_load_spec(
        mesh, definition(axis_direction_stl=(0, 0, 2), start_m=-1, stop_m=1)
    )
    assert spec.selected_geometry_min_m == spec.selected_geometry_max_m == 0
    assert spec.covers_selected_geometry


@pytest.mark.parametrize(
    "origin, direction",
    [
        ((-np.finfo(float).max, 0, 0), (1, 0, 0)),
        ((-np.finfo(float).max, -np.finfo(float).max, 0), (1, 1, 0)),
    ],
)
def test_nonfinite_projection_is_rejected_even_with_explicit_range(
    mesh, origin, direction
):
    if direction == (1, 0, 0):
        # Finite vertices and origin whose subtraction overflows.
        mesh = make_mesh(
            [[1e308, 0, 0], [1e308, 1, 0], [1e308, 0, 1]], [[0, 1, 2]], [2]
        )
    with pytest.raises(NonFiniteError):
        resolve_sectional_load_spec(
            mesh,
            definition(
                axis_origin_stl_m=origin,
                axis_direction_stl=direction,
                start_m=0,
                stop_m=1,
            ),
        )


@pytest.mark.parametrize(
    "bounds, covered",
    [
        ((-4, 6), True),
        ((-5, 8), True),
        ((-4, 5), False),
        ((-3, 6), False),
        ((-1, 1), False),
        ((10, 12), False),
        ((-10, -8), False),
    ],
)
def test_explicit_ranges_are_unclamped_and_coverage_is_geometric(mesh, bounds, covered):
    spec = resolve_sectional_load_spec(
        mesh, definition(start_m=bounds[0], stop_m=bounds[1])
    )
    assert (spec.resolved_start_m, spec.resolved_stop_m) == bounds
    assert (spec.selected_geometry_min_m, spec.selected_geometry_max_m) == (-4, 6)
    assert spec.covers_selected_geometry is covered
    assert spec.all_components_selected


def test_coverage_uses_closed_outer_bounds_without_epsilon(mesh):
    for start, stop in [
        (np.nextafter(-4.0, np.inf), 6),
        (-4, np.nextafter(6.0, -np.inf)),
    ]:
        spec = resolve_sectional_load_spec(mesh, definition(start_m=start, stop_m=stop))
        assert not spec.covers_selected_geometry
    for start, stop in [(0, 1), (-1, 0)]:
        spec = resolve_sectional_load_spec(
            mesh, definition(axis_direction_stl=(0, 0, 1), start_m=start, stop_m=stop)
        )
        assert spec.covers_selected_geometry


@pytest.mark.parametrize("count", [1, 4, 30])
def test_uniform_bin_counts_values_and_endpoints(mesh, count):
    spec = resolve_sectional_load_spec(
        mesh, definition(start_m=-3, stop_m=5, bin_count=count)
    )
    expected = np.array([-3 + 8 * k / count for k in range(count + 1)])
    assert spec.bin_edges_m.shape == (count + 1,)
    assert spec.bin_widths_m.shape == spec.bin_centers_m.shape == (count,)
    assert spec.bin_edges_m[0] == -3
    assert spec.bin_edges_m[-1] == 5
    assert np.all(np.diff(spec.bin_edges_m) > 0)
    assert np.all(spec.bin_widths_m > 0)
    np.testing.assert_allclose(spec.bin_edges_m, expected, rtol=0, atol=2e-15)
    np.testing.assert_array_equal(spec.bin_widths_m, np.diff(spec.bin_edges_m))
    np.testing.assert_allclose(
        spec.bin_centers_m, (expected[:-1] + expected[1:]) / 2, rtol=0, atol=2e-15
    )


@pytest.mark.parametrize(
    "count", [True, False, np.bool_(True), 0, -1, 30.0, 2.5, np.int64(30), "30", None]
)
def test_bin_count_requires_positive_python_integer(count):
    with pytest.raises(ContractValueError):
        definition(bin_count=count)


def test_bin_count_is_required():
    with pytest.raises(TypeError):
        SectionalLoadDefinition(
            axis_origin_stl_m=(0, 0, 0), axis_direction_stl=(1, 0, 0)
        )


@pytest.mark.parametrize(
    "start, stop, count",
    [
        (1e16, 1e16 + 8, 4),
        (1e308, np.nextafter(1e308, np.inf), 1),
        (-1e308, np.nextafter(-1e308, np.inf), 1),
        (-0.0, 0.3, 3),
        (0.1, 0.9, 7),
        (0, np.finfo(float).smallest_subnormal, 1),
    ],
)
def test_large_narrow_and_small_ranges_keep_exact_endpoint_bits(
    mesh, start, stop, count
):
    spec = resolve_sectional_load_spec(
        mesh, definition(start_m=start, stop_m=stop, bin_count=count)
    )
    assert (
        spec.bin_edges_m[[0, -1]].tobytes()
        == np.array([start, stop], dtype=np.float64).tobytes()
    )
    assert np.all(np.isfinite(spec.bin_centers_m))
    assert np.all(spec.bin_widths_m > 0)
    assert np.all(spec.bin_centers_m >= spec.bin_edges_m[:-1])
    assert np.all(spec.bin_centers_m <= spec.bin_edges_m[1:])


def test_safe_bins_allow_overflowing_full_span_when_widths_are_finite(mesh):
    largest = np.finfo(float).max
    spec = resolve_sectional_load_spec(
        mesh, definition(start_m=-largest, stop_m=largest, bin_count=2)
    )
    np.testing.assert_array_equal(spec.bin_edges_m, [-largest, 0, largest])
    np.testing.assert_array_equal(spec.bin_widths_m, [largest, largest])
    np.testing.assert_array_equal(spec.bin_centers_m, [-largest / 2, largest / 2])


@pytest.mark.parametrize("sign", [1, -1])
def test_subnormal_bin_midpoints_do_not_lose_half_width_before_addition(mesh, sign):
    tiny = np.finfo(float).smallest_subnormal
    start, stop = sorted([sign * tiny, sign * 2 * tiny])
    spec = resolve_sectional_load_spec(
        mesh, definition(start_m=start, stop_m=stop, bin_count=1)
    )
    # The exact midpoint is 1.5 subnormal units, which rounds to the even 2.
    np.testing.assert_array_equal(spec.bin_centers_m, [sign * 2 * tiny])


@pytest.mark.parametrize(
    "start, stop, count",
    [
        (1e16, 1e16 + 2, 2),
        (1, np.nextafter(1.0, np.inf), 30),
        (0, np.finfo(float).smallest_subnormal, 2),
        (-np.finfo(float).max, np.finfo(float).max, 1),
        (0, 1, 10**100),
    ],
)
def test_unrepresentable_bins_fail_without_adjusting_count(mesh, start, stop, count):
    item = definition(start_m=start, stop_m=stop, bin_count=count)
    with pytest.raises(ContractError):
        resolve_sectional_load_spec(mesh, item)
    assert item.bin_count == count


def test_auto_ranges_vary_by_geometry_and_explicit_ranges_do_not(mesh):
    other = make_mesh([[10, 0, 0], [12, 0, 0], [10, 2, 0]], [[0, 1, 2]], [2])
    item = definition(component_ids=(2,))
    first, second = (resolve_sectional_load_spec(m, item) for m in (mesh, other))
    np.testing.assert_array_equal(second.bin_edges_m, first.bin_edges_m + 10)
    item = definition(start_m=-5, stop_m=5, component_ids=(2,))
    first, second = (resolve_sectional_load_spec(m, item) for m in (mesh, other))
    np.testing.assert_array_equal(first.bin_edges_m, second.bin_edges_m)
    assert first.covers_selected_geometry
    assert not second.covers_selected_geometry


def test_definition_and_resolved_spec_have_no_mutable_caller_aliases(mesh):
    origin = np.array([1, -2, 3], dtype=np.float32)
    direction = np.array([2, -3, 6], dtype=np.float64)
    ids = [7, 2]
    item = definition(
        axis_origin_stl_m=origin, axis_direction_stl=direction, component_ids=ids
    )
    spec = resolve_sectional_load_spec(mesh, item)
    edges = spec.bin_edges_m.copy()
    origin[:] = 999
    direction[:] = 0
    ids[:] = [11]
    np.testing.assert_array_equal(item.axis_origin_stl_m, [1, -2, 3])
    np.testing.assert_array_equal(item.axis_direction_stl, [2, -3, 6])
    np.testing.assert_allclose(spec.axis_direction_hat_stl, np.array([2, -3, 6]) / 7)
    assert item.component_ids == spec.selected_component_ids == (2, 7)
    np.testing.assert_array_equal(spec.bin_edges_m, edges)
    assert not np.shares_memory(origin, item.axis_origin_stl_m)
    assert not np.shares_memory(direction, item.axis_direction_stl)
    with pytest.raises(FrozenInstanceError):
        item.bin_count = 1
    with pytest.raises(FrozenInstanceError):
        spec.resolved_start_m = 99


def test_component_array_is_copied(mesh):
    ids = np.array([7, 2])
    item = definition(component_ids=ids)
    ids[:] = 11
    assert resolve_sectional_load_spec(mesh, item).selected_component_ids == (2, 7)


@pytest.mark.parametrize("round_trip", [False, True])
def test_all_arrays_are_immutable_even_after_pickle(mesh, round_trip):
    spec = resolve_sectional_load_spec(mesh, definition())
    if round_trip:
        spec = pickle.loads(pickle.dumps(spec))
    arrays = [
        spec.definition.axis_origin_stl_m,
        spec.definition.axis_direction_stl,
        spec.axis_direction_hat_stl,
        spec.bin_edges_m,
        spec.bin_centers_m,
        spec.bin_widths_m,
        spec.selected_face_indices,
    ]
    for array in arrays:
        assert array.flags.c_contiguous
        assert not array.flags.writeable
        assert array.dtype == (
            np.int64 if array is spec.selected_face_indices else np.float64
        )
        with pytest.raises(ValueError):
            array.flat[0] = 42
        with pytest.raises(ValueError):
            array.setflags(write=True)
    assert spec.definition.component_ids is None
    assert spec.selected_component_ids == (2, 7, 11)
    assert spec.covers_selected_geometry


def test_resolving_is_deterministic_and_does_not_mutate_mesh(mesh):
    vertices, faces = mesh.vertices_stl_m.copy(), mesh.faces.copy()
    first = resolve_sectional_load_spec(mesh, definition(component_ids=(11, 2)))
    second = resolve_sectional_load_spec(mesh, definition(component_ids=(2, 11)))
    np.testing.assert_array_equal(first.bin_edges_m, second.bin_edges_m)
    np.testing.assert_array_equal(
        first.selected_face_indices, second.selected_face_indices
    )
    np.testing.assert_array_equal(mesh.vertices_stl_m, vertices)
    np.testing.assert_array_equal(mesh.faces, faces)


def test_resolver_and_direct_spec_constructor_validate_contract_types(mesh):
    for build in (resolve_sectional_load_spec, ResolvedSectionalLoadSpec):
        with pytest.raises(ContractValueError):
            build(object(), definition())
        with pytest.raises(ContractValueError):
            build(mesh, object())
        # Derived state cannot be injected, including arbitrary user edges.
        with pytest.raises(TypeError):
            build(mesh, definition(), bin_edges_m=[0, 1, 3])
