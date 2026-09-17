"""A2 geometry only: analytic integrals and independent conservation oracles."""

from __future__ import annotations

import pickle
import warnings
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal, localcontext
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from panelsolver.core._sectional_geometry import (
    SectionalFragmentGeometry,
    compute_sectional_fragment_geometry,
)
from panelsolver.core.contracts import PanelGeometry
from panelsolver.core.errors import ContractError, ContractValueError, NonFiniteError
from panelsolver.core.mesh import MeshComponent, PanelMesh
from panelsolver.core.mesh_loading import load_panel_mesh
from panelsolver.core.sectional import (
    SectionalLoadDefinition,
    resolve_sectional_load_spec,
)

TRIANGLE = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0]], dtype=np.float64)


def make_mesh(triangles=None, ids=None) -> PanelMesh:
    triangles = np.array([TRIANGLE] if triangles is None else triangles, dtype=float)
    ids = np.zeros(len(triangles), dtype=np.int64) if ids is None else np.array(ids)
    # Deliberately use the loader's adjacent-edge cross and absolute mean.
    crosses = np.cross(
        triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 1]
    )
    norms = np.linalg.norm(crosses, axis=1)
    return PanelMesh(
        triangles.reshape(-1, 3),
        np.arange(triangles.size // 3).reshape(-1, 3),
        PanelGeometry(triangles.mean(axis=1), crosses / norms[:, None], norms / 2, ids),
        tuple(MeshComponent(int(i), f"component-{i}") for i in np.unique(ids)),
    )


def resolve(mesh, **changes):
    inputs = {
        "axis_origin_stl_m": (0, 0, 0),
        "axis_direction_stl": (1, 0, 0),
        "bin_count": 2,
    }
    inputs.update(changes)
    return resolve_sectional_load_spec(mesh, SectionalLoadDefinition(**inputs))


def compute(mesh=None, **changes):
    mesh = make_mesh() if mesh is None else mesh
    return compute_sectional_fragment_geometry(mesh, resolve(mesh, **changes))


def assert_integrals(result, areas, moments):
    np.testing.assert_allclose(result.areas_m2, areas, rtol=1e-13, atol=0)
    np.testing.assert_allclose(
        result.area_first_moments_local_stl_m3, moments, rtol=1e-13, atol=0
    )


def test_analytic_half_triangle_fragments():
    result = compute()
    np.testing.assert_array_equal(result.source_face_indices, [0, 0])
    np.testing.assert_array_equal(result.bin_indices, [0, 1])
    # Integrate x and y over x>=0, y>=0, x+y<=1, split at x=1/2.
    assert_integrals(result, [3 / 8, 1 / 8], [[1 / 12, 7 / 48, 0], [1 / 12, 1 / 48, 0]])


def test_triangle_inside_one_bin_and_full_coverage_empty_bins():
    result = compute(start_m=-1, stop_m=3, bin_count=4)
    np.testing.assert_array_equal(result.bin_indices, [1])
    assert_integrals(result, [1 / 2], [[1 / 6, 1 / 6, 0]])


@pytest.mark.parametrize("count", [3, 17, 257])
def test_many_strips_against_analytic_antiderivatives(count):
    mesh = make_mesh()
    spec = resolve(mesh, bin_count=count)
    result = compute_sectional_fragment_geometry(mesh, spec)
    lo, hi = spec.bin_edges_m[:-1], spec.bin_edges_m[1:]
    # Factor differences to avoid an unnecessarily cancelling analytic oracle.
    width = hi - lo
    areas = width * (1 - (lo + hi) / 2)
    qx = width * ((lo + hi) / 2 - (lo * lo + lo * hi + hi * hi) / 3)
    qy = width / 6 * ((1 - lo) ** 2 + (1 - lo) * (1 - hi) + (1 - hi) ** 2)
    assert_integrals(result, areas, np.column_stack([qx, qy, np.zeros(count)]))


def test_partial_range_analytic_integrals():
    result = compute(start_m=0.25, stop_m=0.75, bin_count=1)
    assert_integrals(result, [1 / 4], [[11 / 96, 13 / 192, 0]])


@pytest.mark.parametrize("bounds", [(-2, -1), (2, 3), (-1, 0), (1, 2)])
def test_no_overlap_line_and_point_contacts_return_valid_empty_geometry(bounds):
    result = compute(start_m=bounds[0], stop_m=bounds[1])
    for name in ("areas_m2", "source_face_indices", "bin_indices"):
        assert getattr(result, name).shape == (0,)
    assert result.origins_stl_m.shape == (0, 3)
    assert result.area_first_moments_local_stl_m3.shape == (0, 3)


@pytest.mark.parametrize(
    "coordinate, bin_index",
    [
        (0.0, 0),
        (np.nextafter(1.0, -np.inf), 0),
        (1.0, 1),
        (np.nextafter(1.0, np.inf), 1),
        (2.0, 1),
    ],
)
def test_whole_boundary_face_and_adjacent_floats_have_exact_ownership(
    coordinate, bin_index
):
    triangle = np.array([[coordinate, 0, 0], [coordinate, 1, 0], [coordinate, 0, 1]])
    result = compute(make_mesh([triangle]), start_m=0, stop_m=2)
    np.testing.assert_array_equal(result.bin_indices, [bin_index])
    assert_integrals(result, [0.5], [[0, 1 / 6, 1 / 6]])


@pytest.mark.parametrize(
    "coordinate", [np.nextafter(0.0, -np.inf), np.nextafter(2.0, np.inf)]
)
def test_whole_face_immediately_outside_outer_boundary_is_not_snapped(coordinate):
    triangle = np.array([[coordinate, 0, 0], [coordinate, 1, 0], [coordinate, 0, 1]])
    assert compute(make_mesh([triangle]), start_m=0, stop_m=2).areas_m2.size == 0


@pytest.mark.parametrize(
    "triangle, bins, areas",
    [
        ([[1, 0, 0], [1, 1, 0], [0, 0, 0]], [0], [0.5]),
        ([[1, 0, 0], [1, 1, 0], [2, 0, 0]], [1], [0.5]),
        ([[0, 0, 0], [1, 1, 0], [2, 0, 0]], [0, 1], [0.5, 0.5]),
        ([[0, 0, 0], [0, 1, 0], [1, 0, 0]], [0], [0.5]),
        ([[1, 0, 0], [2, 1, 0], [2, 0, 0]], [1], [0.5]),
    ],
)
def test_edge_and_vertex_contacts_do_not_double_count(triangle, bins, areas):
    result = compute(make_mesh([triangle]), start_m=0, stop_m=2)
    np.testing.assert_array_equal(result.bin_indices, bins)
    np.testing.assert_allclose(result.areas_m2, areas, rtol=1e-14, atol=0)


def decimal_source_integrals(triangle):
    # Independent high-precision oracle, not stored centroids or production helpers.
    with localcontext() as context:
        context.prec = 80
        points = [[Decimal(float(x)) for x in p] for p in triangle]
        a = [points[1][i] - points[0][i] for i in range(3)]
        b = [points[2][i] - points[0][i] for i in range(3)]
        cross = [a[i] * b[j] - a[j] * b[i] for i, j in [(1, 2), (2, 0), (0, 1)]]
        area = sum(x * x for x in cross).sqrt() / 2
        moment = [area * (a[i] + b[i]) / 3 for i in range(3)]
        # Sum position magnitudes; do not use a possibly cancelled resultant.
        scale = area * (sum(x * x for x in a).sqrt() + sum(x * x for x in b).sqrt()) / 3
        return float(area), np.array([float(x) for x in moment]), float(scale)


def conservation_errors(mesh, spec, result):
    source_areas, source_moments, moment_scales = [], [], []
    area_errors, moment_errors = [], []
    for face in spec.selected_face_indices:
        triangle = mesh.vertices_stl_m[mesh.faces[face]]
        area, moment, scale = decimal_source_integrals(triangle)
        rows = result.source_face_indices == face
        area_error = abs(np.sum(result.areas_m2[rows]) - area)
        moment_error = np.linalg.norm(
            np.sum(result.area_first_moments_local_stl_m3[rows], axis=0) - moment
        )
        assert area_error <= 1e-11 * area
        assert moment_error <= 1e-11 * scale
        source_areas.append(area)
        source_moments.append(moment)
        moment_scales.append(scale)
        area_errors.append(area_error / area)
        moment_errors.append(moment_error / scale)
    global_area_error = abs(np.sum(result.areas_m2) - sum(source_areas))
    assert global_area_error <= 1e-11 * sum(source_areas)
    # Rebase into one common local frame without forming absolute Q. Translation
    # of the entire mesh must not inflate this global first-moment tolerance.
    origins = mesh.vertices_stl_m[mesh.faces[spec.selected_face_indices, 0]]
    common_origin = origins[0]
    relative = result.area_first_moments_local_stl_m3 + result.areas_m2[:, None] * (
        result.origins_stl_m - common_origin
    )
    expected_relative = np.array(source_moments) + np.array(source_areas)[:, None] * (
        origins - common_origin
    )
    global_moment_scale = sum(moment_scales) + np.sum(
        np.array(source_areas) * np.linalg.norm(origins - common_origin, axis=1)
    )
    global_moment_error = np.linalg.norm(
        relative.sum(axis=0) - expected_relative.sum(axis=0)
    )
    assert global_moment_error <= 1e-11 * global_moment_scale
    # Also verify the sum of source-local moments independently.
    assert np.linalg.norm(
        np.sum(result.area_first_moments_local_stl_m3, axis=0)
        - np.sum(source_moments, axis=0)
    ) <= 1e-11 * sum(moment_scales)
    # Also recover the absolute Q identity; this looser absolute check does not
    # replace the translation-independent local first-moment tests above.
    absolute = (
        result.area_first_moments_local_stl_m3
        + result.areas_m2[:, None] * result.origins_stl_m
    )
    expected = np.array(source_moments) + np.array(source_areas)[:, None] * origins
    absolute_scale = np.sum(np.linalg.norm(expected, axis=1))
    assert (
        np.linalg.norm(absolute.sum(axis=0) - expected.sum(axis=0))
        <= 1e-11 * absolute_scale
    )
    return (
        max(area_errors),
        max(moment_errors),
        global_area_error / sum(source_areas),
        global_moment_error / global_moment_scale,
    )


@pytest.mark.parametrize("offset", [0, 1e6, 1e9])
@pytest.mark.parametrize("size", [1.0, 2**-15])
def test_translation_and_small_local_geometry_keep_analytic_first_moments(offset, size):
    origin = np.array([offset, -offset, offset])
    mesh = make_mesh([origin + TRIANGLE * size])
    result = compute(mesh, axis_origin_stl_m=origin)
    assert_integrals(
        result,
        np.array([3 / 8, 1 / 8]) * size**2,
        np.array([[1 / 12, 7 / 48, 0], [1 / 12, 1 / 48, 0]]) * size**3,
    )
    np.testing.assert_array_equal(result.origins_stl_m, [origin, origin])
    conservation_errors(mesh, resolve(mesh, axis_origin_stl_m=origin), result)


@pytest.mark.parametrize("offset", [0, 1e6, 1e9])
def test_real_loader_absolute_centroid_rounding_is_accepted(tmp_path, offset):
    path = tmp_path / "translated.stl"
    triangle = TRIANGLE + [offset, 0, 0]
    vertices = "\n".join(
        "vertex " + " ".join(repr(float(v)) for v in p) for p in triangle
    )
    path.write_text(
        f"solid panel\nfacet normal 0 0 1\nouter loop\n{vertices}\nendloop\nendfacet\nendsolid panel\n"
    )
    mesh = load_panel_mesh([path], 1).mesh
    spec = resolve(mesh, axis_origin_stl_m=(offset, 0, 0))
    result = compute_sectional_fragment_geometry(mesh, spec)
    conservation_errors(mesh, spec, result)
    np.testing.assert_allclose(result.areas_m2, [3 / 8, 1 / 8], rtol=0, atol=0)


def test_oblique_triangle_arbitrary_axis_uses_surface_area():
    # Orthogonal unit basis vectors in an oblique plane; axis has a normal part.
    a = np.array([1, 2, 2]) / 3
    b = np.array([2, 1, -2]) / 3
    normal = np.cross(a, b)
    mesh = make_mesh([[np.zeros(3), a, b]])
    spec = resolve(mesh, axis_direction_stl=a + normal)
    result = compute_sectional_fragment_geometry(mesh, spec)
    np.testing.assert_allclose(result.areas_m2, [3 / 8, 1 / 8], rtol=1e-14, atol=0)
    expected = np.outer([1 / 12, 1 / 12], a) + np.outer([7 / 48, 1 / 48], b)
    np.testing.assert_allclose(
        result.area_first_moments_local_stl_m3, expected, rtol=1e-13, atol=1e-17
    )
    conservation_errors(mesh, spec, result)


@pytest.mark.parametrize("direction", [(1, 0, 0), (2, -3, 1)])
def test_reversing_axis_reverses_physical_bin_integrals(direction):
    mesh = make_mesh([[[0, 0, 0], [3, 1, 0], [1, 4, 2]]])
    first = compute(
        mesh, axis_direction_stl=direction, start_m=-5, stop_m=5, bin_count=20
    )
    second = compute(
        mesh,
        axis_direction_stl=-np.array(direction),
        start_m=-5,
        stop_m=5,
        bin_count=20,
    )
    np.testing.assert_array_equal(first.bin_indices, 19 - second.bin_indices[::-1])
    np.testing.assert_allclose(
        first.areas_m2, second.areas_m2[::-1], rtol=1e-13, atol=0
    )
    np.testing.assert_allclose(
        first.area_first_moments_local_stl_m3,
        second.area_first_moments_local_stl_m3[::-1],
        rtol=1e-13,
        atol=0,
    )


def test_selection_sparse_components_unused_vertices_and_overlapping_faces():
    mesh = make_mesh(
        [TRIANGLE * 2, TRIANGLE, TRIANGLE, TRIANGLE + [3, 0, 0]], [2, 99, 7, 99]
    )
    mesh = replace(
        mesh, vertices_stl_m=np.vstack([mesh.vertices_stl_m, [1e300, -1e300, 1e300]])
    )
    spec = resolve(mesh, component_ids=(99, 7), bin_count=19)
    result = compute_sectional_fragment_geometry(mesh, spec)
    assert set(result.source_face_indices) == {1, 2, 3}
    assert np.sum(result.areas_m2) == pytest.approx(1.5, rel=1e-14)
    conservation_errors(mesh, spec, result)
    # Coincident source faces remain two independent, equal contributions.
    np.testing.assert_array_equal(
        result.areas_m2[result.source_face_indices == 1],
        result.areas_m2[result.source_face_indices == 2],
    )


def test_unselected_invalid_face_is_not_processed_but_selected_outside_face_is_validated():
    mesh = make_mesh([TRIANGLE, TRIANGLE], [2, 7])
    mesh = replace(mesh, faces=[[0, 1, 2], [3, 3, 3]])
    assert compute(mesh, component_ids=(2,)).areas_m2.size == 2
    with pytest.raises(ContractValueError, match="degenerate"):
        compute(mesh, component_ids=(7,), start_m=5, stop_m=6)


@pytest.mark.parametrize("invalid", ["area", "centroid", "degenerate"])
@pytest.mark.parametrize("offset", [0, 1e9])
def test_inconsistent_geometry_rejected_without_repair_or_wide_translation_tolerance(
    invalid, offset
):
    mesh = make_mesh([TRIANGLE + offset])
    if invalid == "area":
        mesh = replace(mesh, geometry=replace(mesh.geometry, areas_m2=[0.5 + 1e-9]))
    elif invalid == "centroid":
        mesh = replace(
            mesh,
            geometry=replace(
                mesh.geometry, centers_stl_m=mesh.geometry.centers_stl_m + [1e-4, 0, 0]
            ),
        )
    else:
        mesh = replace(mesh, faces=[[0, 0, 2]])
    before = mesh.geometry.areas_m2.copy()
    with pytest.raises(ContractValueError):
        compute(mesh, axis_origin_stl_m=(offset, offset, offset), start_m=0, stop_m=1)
    np.testing.assert_array_equal(mesh.geometry.areas_m2, before)


@pytest.mark.parametrize("size", [1e-12, 1e-50])
def test_tiny_source_consistency_has_no_fixed_absolute_area_or_centroid_tolerance(size):
    mesh = make_mesh([TRIANGLE * size])
    conservation_errors(mesh, resolve(mesh), compute(mesh))
    bad_area = replace(
        mesh, geometry=replace(mesh.geometry, areas_m2=mesh.geometry.areas_m2 * 1.001)
    )
    with pytest.raises(ContractValueError, match="area"):
        compute(bad_area)
    bad_center = replace(
        mesh,
        geometry=replace(
            mesh.geometry, centers_stl_m=mesh.geometry.centers_stl_m + size * 1e-5
        ),
    )
    with pytest.raises(ContractValueError, match="centroid"):
        compute(bad_center)


@pytest.mark.parametrize("stop", [1e-14, np.nextafter(0.5, np.inf) - 0.5])
def test_very_small_positive_fragment_retained(stop):
    result = compute(start_m=0, stop_m=stop, bin_count=1)
    assert result.areas_m2.size == 1
    assert result.areas_m2[0] > 0
    assert result.areas_m2[0] == pytest.approx(stop * (1 - stop / 2), rel=1e-14, abs=0)


def test_narrow_representable_strip_and_nextafter_source_vertex():
    lo = 0.5
    hi = np.nextafter(lo, np.inf)
    result = compute(start_m=lo, stop_m=hi, bin_count=1)
    assert result.areas_m2[0] == pytest.approx((hi - lo) / 2, rel=1e-14, abs=0)
    # An immediately adjacent source vertex creates a tiny positive second bin.
    mesh = make_mesh([[[0, 0, 0], [hi, 0, 0], [0, 1, 0]]])
    result = compute(mesh, start_m=0, stop_m=1)
    np.testing.assert_array_equal(result.bin_indices, [0, 1])
    expected = 0.5 * (hi - lo) * ((hi - lo) / hi)
    assert result.areas_m2[1] == pytest.approx(expected, rel=1e-14, abs=0)


@pytest.mark.parametrize("width", [1e-10, 1e-12, 1e-14, np.spacing(0.5)])
def test_oblique_one_ulp_strip_keeps_surface_area_and_first_moment(width):
    a = np.array([1, 2, 2]) / 3
    b = np.array([2, 1, -2]) / 3
    mesh = make_mesh([[np.zeros(3), a, b]])
    lo, hi = 0.5, 0.5 + width
    result = compute(mesh, axis_direction_stl=a, start_m=lo, stop_m=hi, bin_count=1)
    width = hi - lo
    area = width * (1 - (lo + hi) / 2)
    qx = width * ((lo + hi) / 2 - (lo * lo + lo * hi + hi * hi) / 3)
    qy = width / 6 * ((1 - lo) ** 2 + (1 - lo) * (1 - hi) + (1 - hi) ** 2)
    assert_integrals(result, [area], [qx * a + qy * b])


@pytest.mark.parametrize("sign", [1, -1])
def test_narrow_strip_next_to_local_origin_preserves_small_first_moment(sign):
    width = 1e-16
    result = compute(
        axis_direction_stl=(sign, 0, 0),
        start_m=0 if sign == 1 else -width,
        stop_m=width if sign == 1 else 0,
        bin_count=1,
    )
    assert_integrals(
        result,
        [width * (1 - width / 2)],
        [[width**2 / 2 - width**3 / 3, width / 2 - width**2 / 2 + width**3 / 6, 0]],
    )


def test_degenerate_collinear_distinct_vertices_fail():
    mesh = replace(make_mesh(), vertices_stl_m=[[0, 0, 0], [1, 1, 1], [2, 2, 2]])
    with pytest.raises(ContractValueError, match="degenerate"):
        compute(mesh)


@pytest.mark.parametrize("permutation", [(0, 1, 2), (2, 1, 0), (1, 0, 2)])
def test_winding_and_source_vertex_permutations_preserve_physical_integrals(
    permutation,
):
    result = compute(make_mesh([TRIANGLE[list(permutation)]]))
    absolute = (
        result.area_first_moments_local_stl_m3
        + result.areas_m2[:, None] * result.origins_stl_m
    )
    np.testing.assert_allclose(result.areas_m2, [3 / 8, 1 / 8], rtol=1e-14, atol=0)
    np.testing.assert_allclose(
        absolute, [[1 / 12, 7 / 48, 0], [1 / 12, 1 / 48, 0]], rtol=1e-14, atol=0
    )


@pytest.mark.parametrize("kind", ["edge_overflow", "area_overflow", "moment_overflow"])
def test_nonfinite_derived_geometry_is_explicit_error(kind):
    mesh = make_mesh()
    if kind == "edge_overflow":
        vertices = [[-1e308, 0, 0], [1e308, 0, 0], [0, 1, 0]]
    elif kind == "area_overflow":
        vertices = TRIANGLE * 1e160
    else:
        # Valid finite source area ~5e149, but a local first moment overflows.
        vertices = [[0, 0, 0], [1e200, 0, 0], [0, 1e-50, 0]]
        mesh = replace(
            mesh,
            geometry=replace(
                mesh.geometry,
                areas_m2=[5e149],
                centers_stl_m=[[1e200 / 3, 1e-50 / 3, 0]],
            ),
        )
    mesh = replace(mesh, vertices_stl_m=vertices)
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        with pytest.raises(NonFiniteError):
            compute(mesh, axis_direction_stl=(0, 0, 1), start_m=-1, stop_m=1)


def test_unrepresentable_positive_first_moment_is_not_silently_zero():
    # Valid ordinary source; fragment area ~1e-200 but Qx ~5e-401.
    with pytest.raises(ContractValueError, match="first moment underflow"):
        compute(start_m=0, stop_m=1e-200, bin_count=1)


def test_unrepresentable_positive_fragment_area_is_not_silently_skipped():
    mesh = make_mesh([[[0, 0, 0], [1, 0, 0], [1, 1e-140, 0]]])
    with pytest.raises(ContractValueError, match="positive area underflow"):
        compute(mesh, start_m=0, stop_m=1e-180, bin_count=1)


def test_fixed_seed_randomized_conservation_and_determinism():
    rng = np.random.default_rng(304_002)
    triangles = rng.uniform(-2, 2, (32, 3, 3))
    mesh = make_mesh(triangles, np.tile([2, 7, 99, 7], 8))
    for direction in rng.normal(size=(8, 3)):
        spec = resolve(
            mesh, axis_direction_stl=direction, bin_count=43, component_ids=(99, 7)
        )
        first = compute_sectional_fragment_geometry(mesh, spec)
        conservation_errors(mesh, spec, first)
        second = compute_sectional_fragment_geometry(mesh, spec)
        for field in fields(first):
            np.testing.assert_array_equal(
                getattr(first, field.name), getattr(second, field.name)
            )


def test_candidate_bins_do_not_clip_every_face_against_every_bin():
    mesh = make_mesh()
    spec = resolve(mesh, start_m=0, stop_m=1e6, bin_count=100_000)
    from panelsolver.core import _sectional_geometry

    with patch.object(
        _sectional_geometry,
        "_band_integrals",
        wraps=_sectional_geometry._band_integrals,
    ) as split:
        result = compute_sectional_fragment_geometry(mesh, spec)
    assert split.call_count <= 2
    assert result.areas_m2.shape == (1,)


@pytest.mark.parametrize("round_trip", [False, True])
def test_result_buffers_are_frozen_and_have_no_mutable_aliases(round_trip):
    result = compute()
    inputs = {
        field.name: getattr(result, field.name).copy() for field in fields(result)
    }
    owned = SectionalFragmentGeometry(**inputs)
    if round_trip:
        owned = pickle.loads(pickle.dumps(owned))
    for name, value in inputs.items():
        array = getattr(owned, name)
        assert array.dtype == (np.int64 if name.endswith("indices") else np.float64)
        assert array.flags.c_contiguous
        assert not np.shares_memory(array, value)
        value[:] = 99
        np.testing.assert_array_equal(array, getattr(result, name))
        with pytest.raises(ValueError):
            array.setflags(write=True)
        with pytest.raises(ValueError):
            array.flat[0] = 0
    with pytest.raises(FrozenInstanceError):
        owned.areas_m2 = np.ones(2)


@pytest.mark.parametrize(
    "changes",
    [
        {"areas_m2": [0, 1]},
        {"areas_m2": [-1, 1]},
        {"areas_m2": [np.inf, 1]},
        {"areas_m2": [True, False]},
        {"areas_m2": [1]},
        {"bin_indices": [1, 0]},
        {"bin_indices": [0, 0]},
        {"bin_indices": [0.0, 1.0]},
        {"source_face_indices": [1, 0]},
        {"origins_stl_m": [0, 0, 0]},
        {"area_first_moments_local_stl_m3": [[np.nan, 0, 0], [0, 0, 0]]},
    ],
)
def test_fragment_contract_rejects_invalid_shape_values_and_order(changes):
    with pytest.raises(ContractError):
        replace(compute(), **changes)


def test_geometry_entry_point_requires_mesh_and_resolved_spec():
    mesh = make_mesh()
    with pytest.raises(ContractValueError):
        compute_sectional_fragment_geometry(object(), resolve(mesh))
    with pytest.raises(ContractValueError):
        compute_sectional_fragment_geometry(mesh, object())


def test_real_repository_meshes_satisfy_geometry_boundary():
    root = Path(__file__).parents[1] / "fixtures" / "phase1" / "inputs" / "stl"
    for path in sorted(root.glob("*.stl")):
        mesh = load_panel_mesh([path], 1).mesh
        spec = resolve(mesh, axis_direction_stl=(2, -3, 1), bin_count=11)
        conservation_errors(mesh, spec, compute_sectional_fragment_geometry(mesh, spec))
