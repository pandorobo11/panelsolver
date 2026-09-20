"""A3 analytic loads, independent conservation, models, and immutable handoff."""

from __future__ import annotations

import math
import pickle
import warnings
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from trimesh.ray import has_embree

from panelsolver.core._sectional_geometry import compute_sectional_fragment_geometry
from panelsolver.core._sectional_integration import (
    SectionalComponentDistribution,
    SectionalLoadDistribution,
    integrate_sectional_loads,
)
from panelsolver.core.aggregation import aggregate_component_results
from panelsolver.core.contracts import (
    CommonCasePayload,
    LocalLoads,
    ModelCasePayload,
    PanelFlowState,
)
from panelsolver.core.errors import ContractError, ContractValueError, NonFiniteError
from panelsolver.core.frames import stability_alpha_deg
from panelsolver.core.integration import _integrated_coefficients, integrate_panel_loads
from panelsolver.core.mesh_loading import load_panel_mesh
from panelsolver.core.shielding import ShieldingConfig, compute_shielding
from panelsolver.models import HypersonicModel, SentmanModel
from tests.sectional_load_oracle import assert_conservation, sum_bins

from .test_sectional_geometry import TRIANGLE, make_mesh, resolve


def common_case(**changes):
    values = {
        "case_id": "sectional-test",
        "Aref_m2": 1.0,
        "moment_reference_stl_m": [0, 0, 0],
        "Lref_Cl_m": 1.0,
        "Lref_Cm_m": 1.0,
        "Lref_Cn_m": 1.0,
        "alpha_stability_deg": 0.0,
    }
    return CommonCasePayload(**(values | changes))


def integrate(mesh=None, loads=None, case=None, **definition):
    mesh = make_mesh() if mesh is None else mesh
    loads = LocalLoads([[0, 0, -1]]) if loads is None else loads
    case = common_case() if case is None else case
    return integrate_sectional_loads(mesh, resolve(mesh, **definition), loads, case)


def assert_components_and_baseline(mesh, loads, case, result, flow=None):
    if flow is None:
        flow = PanelFlowState([1, 0, 0], np.zeros(mesh.n_faces, dtype=bool))
    old = integrate_panel_loads(mesh.geometry, loads, case)
    components = {
        item.component_id: item.integrated
        for item in aggregate_component_results(mesh.geometry, flow, old, case)
    }
    for item in result.components:
        faces = np.flatnonzero(mesh.face_component_ids == item.component_id)
        assert_conservation(
            mesh, loads, case, faces, item.distribution, components[item.component_id]
        )
    faces = result.spec.selected_face_indices
    baseline = (
        old.total
        if result.spec.all_components_selected
        else _integrated_coefficients(
            sum_bins(old.face_force_coeff_stl[faces]),
            sum_bins(old.face_moment_area_coeff_body_m[faces]),
            case,
        )
    )
    report = assert_conservation(mesh, loads, case, faces, result.total, baseline)
    for field in fields(result.total):
        arrays = np.stack(
            [getattr(item.distribution, field.name) for item in result.components]
        )
        # Local absolute contribution scale also covers cancellation in a bin.
        total = getattr(result.total, field.name)
        assert np.all(
            np.abs(np.sum(arrays, axis=0) - total)
            <= 1e-14 * np.sum(np.abs(arrays), axis=0)
        )
    return report


def test_one_face_analytic_force_moment_and_coefficient_views():
    # Local first moments: (1/12,7/48,0), (1/12,1/48,0).
    case = common_case(
        Aref_m2=2,
        moment_reference_stl_m=[1, -2, 3],
        Lref_Cl_m=2,
        Lref_Cm_m=3,
        Lref_Cn_m=5,
        alpha_stability_deg=30,
    )
    loads = LocalLoads([[2, 3, -4]], cell_scalars={"cp": [999]})
    result = integrate(loads=loads, case=case)
    d = result.total
    np.testing.assert_array_equal(d.wetted_area_m2, [3 / 8, 1 / 8])
    expected_force = np.array([[3 / 8, 9 / 16, -3 / 4], [1 / 8, 3 / 16, -1 / 4]])
    # cross(T(Q-A*reference), T(traction))/Aref, evaluated as fixed rationals.
    expected_moment = np.array([[5 / 48, -41 / 24, 4 / 3], [-1 / 48, -11 / 24, 1 / 3]])
    np.testing.assert_allclose(d.force_coeff_stl, expected_force, rtol=1e-14, atol=0)
    np.testing.assert_allclose(
        d.moment_area_coeff_body_m, expected_moment, rtol=1e-14, atol=0
    )
    body = expected_force * [-1, 1, -1]
    np.testing.assert_array_equal(d.force_coeff_body, body)
    c, s = math.sqrt(3) / 2, 0.5
    stability = np.column_stack(
        [body[:, 0] * c + body[:, 2] * s, body[:, 1], -body[:, 0] * s + body[:, 2] * c]
    )
    np.testing.assert_allclose(d.force_coeff_stability, stability, rtol=1e-14, atol=0)
    for name, expected in {
        "CA": -body[:, 0],
        "CY": body[:, 1],
        "CN": -body[:, 2],
        "CD": -stability[:, 0],
        "CL": -stability[:, 2],
        "Cl": expected_moment[:, 0] / 2,
        "Cm": expected_moment[:, 1] / 3,
        "Cn": expected_moment[:, 2] / 5,
    }.items():
        np.testing.assert_allclose(getattr(d, name), expected, rtol=1e-14, atol=0)
    assert_components_and_baseline(make_mesh(), loads, case, result)


def test_partial_range_has_independent_analytic_area_force_and_offset_moment():
    # Integral on 1/4 <= x <= 3/4: A=1/4, Qx=11/96, Qy=13/192.
    result = integrate(
        case=common_case(moment_reference_stl_m=[1, -2, 3]),
        start_m=0.25,
        stop_m=0.75,
        bin_count=1,
    )
    assert not result.spec.covers_selected_geometry
    np.testing.assert_array_equal(result.total.wetted_area_m2, [1 / 4])
    np.testing.assert_allclose(
        result.total.force_coeff_stl, [[0, 0, -1 / 4]], rtol=1e-14, atol=0
    )
    np.testing.assert_allclose(
        result.total.moment_area_coeff_body_m,
        [[109 / 192, -13 / 96, 0]],
        rtol=1e-14,
        atol=0,
    )


@pytest.mark.parametrize("offset", [0.0, 1e6])
def test_required_translated_triangle_local_accuracy_and_independent_stored_budget(
    offset,
):
    origin = [offset, 0, 0]
    mesh = make_mesh([TRIANGLE + origin])
    loads, case = LocalLoads([[0, 0, -1]]), common_case(moment_reference_stl_m=origin)
    result = integrate(mesh, loads, case, axis_origin_stl_m=origin)
    np.testing.assert_array_equal(result.total.wetted_area_m2, [3 / 8, 1 / 8])
    np.testing.assert_allclose(result.total.Cl, [7 / 48, 1 / 48], rtol=1e-14, atol=0)
    np.testing.assert_allclose(result.total.Cm, [1 / 12, 1 / 12], rtol=1e-14, atol=0)
    assert math.fsum(result.total.Cm) == pytest.approx(1 / 6, rel=1e-14, abs=0)
    report = assert_components_and_baseline(mesh, loads, case, result)
    if offset:
        assert report["moment_stored_error"] > report["moment_tolerance"]
        assert report["moment_budget"] > report["moment_tolerance"]
        assert report["moment_local_error"] < report["moment_tolerance"]
    else:
        assert report["moment_stored_error"] < report["moment_tolerance"]


@pytest.mark.parametrize("size", [1e-12, 1e-40, 1, 1e10])
def test_local_tolerances_follow_geometry_scale(size):
    mesh = make_mesh([TRIANGLE * size])
    case = common_case(moment_reference_stl_m=np.array([0.25, -0.5, 0.125]) * size)
    loads = LocalLoads([[1, 2, -3]])
    result = integrate(mesh, loads, case, bin_count=37)
    assert_components_and_baseline(mesh, loads, case, result)


def test_oblique_section_axis_in_three_dimensions_has_analytic_bins():
    a, b = np.array([1, 2, 2]) / 3, np.array([2, 1, -2]) / 3
    origin = np.array([3.0, -2.0, 4.0])
    mesh = make_mesh([[origin, origin + a, origin + b]])
    loads, case = LocalLoads([[0, 0, -1]]), common_case(moment_reference_stl_m=origin)
    result = integrate(
        mesh,
        loads,
        case,
        axis_origin_stl_m=origin,
        axis_direction_stl=a,
        start_m=0,
        stop_m=1,
        bin_count=2,
    )
    np.testing.assert_allclose(
        result.total.wetted_area_m2, [3 / 8, 1 / 8], rtol=1e-14, atol=0
    )
    # Qx=a_x/12+b_x*(7/48,1/48); Qy similarly. T(Q x tau)=(Qy,Qx,0).
    np.testing.assert_allclose(
        result.total.moment_area_coeff_body_m,
        [[5 / 48, 1 / 8, 0], [1 / 16, 1 / 24, 0]],
        rtol=1e-14,
        atol=0,
    )


@pytest.mark.parametrize("bounds", [(-2, -1), (2, 3), (-1, 0), (1, 2)])
def test_nonintersecting_explicit_range_returns_all_bins_and_components(bounds):
    result = integrate(start_m=bounds[0], stop_m=bounds[1], bin_count=7)
    assert not result.spec.covers_selected_geometry
    assert len(result.components) == 1
    for distribution in (result.total, result.components[0].distribution):
        for field in fields(distribution):
            values = getattr(distribution, field.name)
            assert values.shape == ((7,) if field.name == "wetted_area_m2" else (7, 3))
            np.testing.assert_array_equal(values, np.zeros_like(values))


@pytest.mark.parametrize("selection", [(7,), (99, 7), None])
@pytest.mark.parametrize("explicit", [False, True])
def test_sparse_components_selection_overlap_empty_bins_and_conservation(
    selection, explicit
):
    mesh = make_mesh(
        [TRIANGLE, TRIANGLE + [3, 0, 0], TRIANGLE, TRIANGLE + [3, 0, 0]], [7, 99, 2, 7]
    )
    loads = LocalLoads([[1, 2, -3], [-4, 5, 6], [7, -8, 9], [2, -3, 1]])
    case = common_case(
        Aref_m2=2.3,
        moment_reference_stl_m=[0.2, -1, 2],
        Lref_Cl_m=0.7,
        Lref_Cm_m=3,
        Lref_Cn_m=4,
        alpha_stability_deg=143,
    )
    bounds = {"start_m": -1, "stop_m": 5} if explicit else {}
    result = integrate(
        mesh, loads, case, component_ids=selection, bin_count=12, **bounds
    )
    assert tuple(item.component_id for item in result.components) == tuple(
        sorted(selection or (2, 7, 99))
    )
    assert result.spec.covers_selected_geometry
    assert len(result.components) == len(selection or (2, 7, 99))
    assert np.any(result.total.wetted_area_m2 == 0)
    for item in result.components:
        empty = item.distribution.wetted_area_m2 == 0
        for field in fields(item.distribution):
            np.testing.assert_array_equal(
                getattr(item.distribution, field.name)[empty], 0
            )
    if selection != (7,):
        last = result.components[-1].distribution
        assert np.any((last.wetted_area_m2 == 0) & (result.total.wetted_area_m2 > 0))
        occupied = np.stack(
            [item.distribution.wetted_area_m2 > 0 for item in result.components]
        )
        assert np.any(occupied.sum(axis=0) > 1)
    assert_components_and_baseline(mesh, loads, case, result)


@pytest.mark.parametrize(
    "direction, angle",
    [
        ([1, 0, 0], 0),
        ([-1, 0, 0], 180),
        ([-math.sqrt(3) / 2, 0, 0.5], 150),
        ([0, -1, 0], 0),
        ([1e-16, 1, 1e-16], 0),
    ],
)
def test_resolved_forward_backward_and_lateral_stability_frames(direction, angle):
    case = common_case(alpha_stability_deg=stability_alpha_deg(direction))
    assert case.alpha_stability_deg == pytest.approx(angle, abs=1e-13)
    d = integrate(loads=LocalLoads([[2, 3, -4]]), case=case).total
    ca, cn = np.array([3 / 4, 1 / 4]), np.array([-1.5, -0.5])
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    np.testing.assert_allclose(d.CD, ca * c + cn * s, rtol=1e-14, atol=1e-15)
    np.testing.assert_allclose(d.CL, -ca * s + cn * c, rtol=1e-14, atol=1e-15)
    np.testing.assert_array_equal(d.CY, [9 / 8, 3 / 8])


def model_case(kind):
    if kind == "hypersonic":
        return HypersonicModel(), ModelCasePayload(
            kind,
            {
                "Mach": 6.0,
                "gamma": 1.4,
                "windward_eq": "newtonian",
                "leeward_eq": "shield",
            },
        )
    return SentmanModel(), ModelCasePayload(
        kind,
        {"S": 10.0, "Ti_K": 1000.0, "Tw_K": 1000.0, "Mach": None, "Altitude_km": None},
    )


@pytest.mark.parametrize("kind", ["hypersonic", "sentman"])
def test_models_preserve_normal_and_tangential_traction_and_shielded_surface(kind):
    # Two coincident source triangles are separate components; only one shielded.
    mesh = make_mesh([TRIANGLE, TRIANGLE], [2, 7])
    flow = PanelFlowState([math.sqrt(3) / 2, 0, -0.5], [False, True])
    model, payload = model_case(kind)
    loads = model.evaluate(mesh.geometry, flow, payload)
    case = common_case(alpha_stability_deg=stability_alpha_deg(flow.velocity_hat_stl))
    result = integrate(mesh, loads, case)
    active, shielded = (item.distribution for item in result.components)
    np.testing.assert_array_equal(loads.traction_coeff_stl[1], [0, 0, 0])
    np.testing.assert_array_equal(shielded.wetted_area_m2, [3 / 8, 1 / 8])
    for field in fields(shielded):
        if field.name != "wetted_area_m2":
            np.testing.assert_array_equal(
                getattr(shielded, field.name), np.zeros((2, 3))
            )
    np.testing.assert_array_equal(result.total.wetted_area_m2, [3 / 4, 1 / 4])
    np.testing.assert_allclose(
        active.force_coeff_stl,
        np.array([3 / 8, 1 / 8])[:, None] * loads.traction_coeff_stl[0],
        rtol=1e-14,
        atol=0,
    )
    if kind == "sentman":
        assert loads.traction_coeff_stl[0, 0] > 0
        assert np.all(active.force_coeff_stl[:, 0] > 0)
        assert np.all(active.Cn != 0)  # Tangential force's nonzero yaw moment.
        np.testing.assert_allclose(
            active.Cn,
            np.array([7 / 48, 1 / 48]) * loads.traction_coeff_stl[0, 0],
            rtol=1e-14,
            atol=0,
        )
    else:
        np.testing.assert_array_equal(active.force_coeff_stl[:, :2], np.zeros((2, 2)))
        np.testing.assert_allclose(
            active.force_coeff_stl[:, 2], [-3 / 16, -1 / 16], rtol=1e-14, atol=0
        )
    assert_components_and_baseline(mesh, loads, case, result, flow)


@pytest.mark.parametrize("backend", ["rtree", "embree"])
@pytest.mark.parametrize("kind", ["hypersonic", "sentman"])
def test_real_mesh_models_and_backends_conserve_whole_case_and_components(
    kind, backend
):
    if backend == "embree" and not has_embree:
        pytest.skip("Embree is unavailable")
    root = Path(__file__).parents[1] / "fixtures" / "phase1" / "inputs" / "stl"
    mesh = load_panel_mesh([root / "double_plate.stl", root / "cube.stl"], 1).mesh
    velocity = np.array([math.sqrt(3) / 2, 0, 0.5])
    shielding = compute_shielding(mesh, velocity, ShieldingConfig(ray_backend=backend))
    assert shielding.config.effective_backend == backend
    assert np.any(shielding.shielded)
    flow = PanelFlowState(velocity, shielding.shielded)
    model, payload = model_case(kind)
    loads = model.evaluate(mesh.geometry, flow, payload)
    np.testing.assert_array_equal(loads.traction_coeff_stl[shielding.shielded], 0)
    case = common_case(
        Aref_m2=3.4,
        moment_reference_stl_m=[0.2, -0.3, 0.4],
        Lref_Cl_m=0.6,
        Lref_Cm_m=2,
        Lref_Cn_m=3,
        alpha_stability_deg=30,
    )
    result = integrate(mesh, loads, case, axis_direction_stl=[2, -3, 1], bin_count=57)
    assert result.spec.all_components_selected and result.spec.covers_selected_geometry
    assert_components_and_baseline(mesh, loads, case, result, flow)


@pytest.mark.parametrize("offset", [0, 1e6])
def test_fixed_seed_many_fragments_local_and_stored_conservation_and_determinism(
    offset,
):
    rng = np.random.default_rng(304003)
    # Dyadic local coordinates remain exactly the same under translation.
    triangles = rng.integers(-128, 129, (24, 3, 3)) / 32 + np.array(
        [offset, -offset, offset]
    )
    mesh = make_mesh(triangles, np.tile([2, 7, 99], 8))
    loads = LocalLoads(rng.normal(size=(24, 3)))
    case = common_case(
        Aref_m2=4.1,
        moment_reference_stl_m=[offset + 0.25, -offset - 0.5, offset + 0.125],
        Lref_Cl_m=0.5,
        Lref_Cm_m=3,
        Lref_Cn_m=7,
        alpha_stability_deg=127,
    )
    definition = {
        "axis_origin_stl_m": [offset, -offset, offset],
        "axis_direction_stl": [2, -3, 1],
        "bin_count": 257,
    }
    first, second = (
        integrate(mesh, loads, case, **definition),
        integrate(mesh, loads, case, **definition),
    )
    assert_components_and_baseline(mesh, loads, case, first)
    for a, b in zip(
        (first.total, *(x.distribution for x in first.components)),
        (second.total, *(x.distribution for x in second.components)),
        strict=True,
    ):
        for field in fields(a):
            np.testing.assert_array_equal(
                getattr(a, field.name), getattr(b, field.name)
            )


@pytest.mark.parametrize("separate_components", [False, True])
def test_cancellation_prone_fragment_reduction_keeps_small_force_and_moment(
    separate_components,
):
    # Sequential addition loses the middle contribution in each 1e16,1,-1e16 triple.
    ids = np.tile([2, 7, 99], 100) if separate_components else None
    mesh = make_mesh(np.tile(TRIANGLE, (300, 1, 1)), ids)
    traction = np.zeros((300, 3))
    traction[:, 2] = np.tile([1e16, 1, -1e16], 100)
    result = integrate(mesh, LocalLoads(traction), bin_count=2)
    np.testing.assert_array_equal(result.total.force_coeff_stl[:, 2], [37.5, 12.5])
    np.testing.assert_allclose(
        result.total.Cm, [-100 / 12, -100 / 12], rtol=1e-14, atol=0
    )


def test_geometry_runs_once_and_large_empty_output_does_not_create_dummy_fragments():
    mesh = make_mesh()
    spec = resolve(mesh, start_m=-1, stop_m=9999, bin_count=10_000)
    with patch(
        "panelsolver.core._sectional_integration.compute_sectional_fragment_geometry",
        wraps=compute_sectional_fragment_geometry,
    ) as geometry:
        result = integrate_sectional_loads(
            mesh, spec, LocalLoads([[0, 0, -1]]), common_case()
        )
    geometry.assert_called_once_with(mesh, spec)
    assert np.count_nonzero(result.total.wetted_area_m2) == 1
    np.testing.assert_array_equal(result.total.wetted_area_m2[1], 0.5)


@pytest.mark.parametrize("roundtrip", [False, True])
def test_result_arrays_and_views_are_owned_immutable_and_pickle_safe(roundtrip):
    result = integrate()
    inputs = {
        field.name: getattr(result.total, field.name).copy()
        for field in fields(result.total)
    }
    distribution = SectionalLoadDistribution(**inputs)
    result = replace(result, total=distribution, components=list(result.components))
    if roundtrip:
        result = pickle.loads(pickle.dumps(result))
    assert isinstance(result.components, tuple)
    for name, value in inputs.items():
        array = getattr(result.total, name)
        assert not np.shares_memory(array, value)
        value[:] = 999
        assert not np.any(array == 999)
    for distribution in (result.total, result.components[0].distribution):
        for name in [field.name for field in fields(distribution)] + [
            "CA",
            "CY",
            "CN",
            "CD",
            "CL",
            "Cl",
            "Cm",
            "Cn",
        ]:
            array = getattr(distribution, name)
            assert array.dtype == np.float64
            with pytest.raises(ValueError):
                array.setflags(write=True)
            with pytest.raises(ValueError):
                array.flat[0] = 0
    with pytest.raises(FrozenInstanceError):
        result.total = distribution


@pytest.mark.parametrize("position", range(4))
def test_input_contract_types_are_checked(position):
    mesh = make_mesh()
    args = [mesh, resolve(mesh), LocalLoads([[0, 0, -1]]), common_case()]
    args[position] = object()
    with pytest.raises(ContractValueError):
        integrate_sectional_loads(*args)


def test_mismatched_panel_count_and_component_selection_rejected():
    with pytest.raises(ContractValueError):
        integrate(loads=LocalLoads([[0, 0, -1], [0, 0, -1]]))
    mesh = make_mesh([TRIANGLE, TRIANGLE], [2, 7])
    with pytest.raises(ContractValueError):
        integrate_sectional_loads(
            make_mesh(), resolve(mesh), LocalLoads([[0, 0, -1]]), common_case()
        )
    with pytest.raises(ContractValueError):
        integrate_sectional_loads(
            make_mesh([TRIANGLE, TRIANGLE], [9, 11]),
            resolve(mesh),
            LocalLoads([[0, 0, -1], [0, 0, -1]]),
            common_case(),
        )


@pytest.mark.parametrize("bad", ["type", "face", "bin", "selection"])
def test_a2_output_indices_are_checked_before_traction_or_component_lookup(bad):
    mesh = make_mesh([TRIANGLE, TRIANGLE], [2, 7])
    spec = resolve(mesh, component_ids=(2,))
    fragments = compute_sectional_fragment_geometry(mesh, spec)
    if bad == "type":
        fragments = object()
    elif bad == "face":
        fragments = replace(fragments, source_face_indices=[2, 2])
    elif bad == "bin":
        fragments = replace(fragments, bin_indices=[0, 2])
    else:
        fragments = replace(fragments, source_face_indices=[1, 1])
    with patch(
        "panelsolver.core._sectional_integration.compute_sectional_fragment_geometry",
        return_value=fragments,
    ):
        with pytest.raises(ContractValueError):
            integrate_sectional_loads(
                mesh, spec, LocalLoads([[0, 0, -1], [0, 0, -2]]), common_case()
            )


@pytest.mark.parametrize(
    "changes",
    [
        {"wetted_area_m2": [-1, 0]},
        {"wetted_area_m2": []},
        {"force_coeff_stl": [1, 2, 3]},
        {"moment_coeff_body": [[np.nan, 0, 0], [0, 0, 0]]},
        {"force_coeff_body": [[True, False, True], [False, True, False]]},
    ],
)
def test_distribution_rejects_malformed_values_and_shapes(changes):
    with pytest.raises(ContractError):
        replace(integrate().total, **changes)


def test_result_rejects_inconsistent_bins_ids_and_types():
    result = integrate()
    for changes in (
        {"spec": object()},
        {"case": object()},
        {"total": object()},
        {"components": None},
        {"components": [object()]},
        {"components": ()},
        {"components": (SectionalComponentDistribution(99, result.total),)},
        {"total": integrate(bin_count=3).total},
    ):
        with pytest.raises(ContractError):
            replace(result, **changes)
    with pytest.raises(ContractError):
        SectionalComponentDistribution(True, result.total)
    with pytest.raises(ContractError):
        SectionalComponentDistribution(0, object())


@pytest.mark.parametrize(
    "changes,traction",
    [
        ({"Aref_m2": 1e-309}, [1, 2, 3]),
        ({"moment_reference_stl_m": [1e308, 1e308, 0]}, [10, 10, -10]),
        ({"Lref_Cm_m": 1e-310}, [0, 0, -1]),
    ],
)
def test_overflowed_derived_loads_fail_explicitly_without_runtime_warnings(
    changes, traction
):
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        with pytest.raises(NonFiniteError):
            integrate(loads=LocalLoads([traction]), case=common_case(**changes))
