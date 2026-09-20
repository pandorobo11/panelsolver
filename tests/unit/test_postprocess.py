from __future__ import annotations

import inspect
import pickle
import re
import shutil
from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, is_dataclass, replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from panelsolver import (
    FMFCase,
    HypersonicCase,
    SolveResult,
    resolve_attitude,
    solve_fmf,
    solve_hypersonic,
)
from panelsolver.core import execute_case
from panelsolver.core._sectional_integration import integrate_sectional_loads
from panelsolver.core.sectional import resolve_sectional_load_spec
from panelsolver.postprocess import SectionalLoads, compute_sectional_loads

PLATE = Path(__file__).parents[1] / "fixtures/phase1/inputs/stl/plate.stl"
DEFINITION = {
    "axis_origin_stl_m": (0.2, -0.1, 0.4),
    "axis_direction_stl": (0.2, 0.9, 0.4),
    "bin_count": 7,
}
VECTORS = (
    "force_coeff_stl",
    "force_coeff_body",
    "force_coeff_stability",
    "moment_area_coeff_body_m",
    "moment_coeff_body",
)


def _case(domain, path):
    common = {
        "case_id": f"postprocess-{domain}",
        "stl_paths": (path, path),
        "stl_scale_m_per_unit": 1.0,
        "attitude": resolve_attitude(18.0, 11.0),
        "Aref_m2": 2.7,
        "moment_reference_stl_m": (0.3, -0.2, 0.7),
        "Lref_Cl_m": 1.5,
        "Lref_Cm_m": 2.3,
        "Lref_Cn_m": 3.1,
    }
    if domain == "fmf":
        return FMFCase(
            **common,
            speed_ratio=5.0,
            translational_temperature_k=900.0,
            wall_temperature_k=300.0,
        )
    return HypersonicCase(**common, mach=6.0, gamma=1.4)


def _solve(domain, path=PLATE):
    solve = solve_fmf if domain == "fmf" else solve_hypersonic
    return solve(_case(domain, path))


def _arrays(value):
    if isinstance(value, np.ndarray):
        yield value
    elif is_dataclass(value):
        for field in fields(value):
            yield from _arrays(getattr(value, field.name))
    elif isinstance(value, tuple):
        for item in value:
            yield from _arrays(item)


@pytest.mark.parametrize("domain", ("fmf", "hypersonic"))
def test_retains_exact_execution_and_matches_a3(domain):
    executions = []

    def record(request):
        execution = execute_case(request)
        executions.append(execution)
        return execution

    with patch("panelsolver.api.execute_case", side_effect=record) as execute:
        result = _solve(domain)
        loads = compute_sectional_loads(result, **DEFINITION)
        partial = compute_sectional_loads(
            result, **DEFINITION, start_m=-0.3, stop_m=0.2, component_ids=(1,)
        )
    assert execute.call_count == 1
    execution = executions[0]
    context = result._sectional_context
    assert context.mesh is execution.mesh
    assert context.mesh.geometry is result.geometry
    assert context.case is execution.results.case
    assert loads.case is execution.results.case
    assert loads.case_signature == result.case_signature == execution.signature.digest
    assert loads.case.case_id == f"postprocess-{domain}"
    assert loads.case.alpha_stability_deg == result.attitude.alpha_stability_deg
    assert loads.case.Aref_m2 == 2.7
    assert (loads.case.Lref_Cl_m, loads.case.Lref_Cm_m, loads.case.Lref_Cn_m) == (
        1.5,
        2.3,
        3.1,
    )
    np.testing.assert_array_equal(loads.case.moment_reference_stl_m, (0.3, -0.2, 0.7))
    for actual in (loads, partial):
        expected = integrate_sectional_loads(
            execution.mesh,
            resolve_sectional_load_spec(execution.mesh, actual.spec.definition),
            execution.results.local_loads,
            execution.results.case,
        )
        assert isinstance(actual, SectionalLoads)
        for got, wanted in zip(_arrays(actual), _arrays(expected), strict=True):
            np.testing.assert_array_equal(got, wanted)
    assert loads.spec.all_components_selected
    assert loads.spec.covers_selected_geometry
    assert partial.spec.selected_component_ids == (1,)
    assert not partial.spec.all_components_selected
    assert not partial.spec.covers_selected_geometry
    assert len(partial.components) == 1
    for name in VECTORS:
        np.testing.assert_allclose(
            getattr(loads.total, name).sum(axis=0),
            getattr(result.coefficients, name),
            rtol=1e-12,
            atol=1e-14,
        )


@pytest.mark.parametrize("domain", ("fmf", "hypersonic"))
def test_postprocess_never_rereads_changed_or_deleted_stl(domain, tmp_path):
    source = tmp_path / "model.stl"
    shutil.copyfile(PLATE, source)
    result = _solve(domain, source)
    original = compute_sectional_loads(result, **DEFINITION)
    source.write_text("replaced by an invalid STL", encoding="utf-8")
    with (
        patch("panelsolver.api.execute_case", side_effect=AssertionError("re-solve")),
        patch(
            "panelsolver.core.execution.load_panel_mesh",
            side_effect=AssertionError("STL reread"),
        ),
    ):
        replaced = compute_sectional_loads(result, **DEFINITION)
        source.unlink()
        deleted = compute_sectional_loads(result, **DEFINITION)
    for actual in (replaced, deleted):
        for got, wanted in zip(_arrays(actual), _arrays(original), strict=True):
            np.testing.assert_array_equal(got, wanted)


def test_original_constructor_and_missing_context_are_explicit():
    original = _solve("hypersonic")
    names = tuple(inspect.signature(SolveResult).parameters)
    assert names == (
        "attitude",
        "coefficients",
        "components",
        "geometry",
        "flow_state",
        "local_loads",
        "case_signature",
        "ray_backend_used",
        "warnings",
    )
    manual = SolveResult(*(getattr(original, name) for name in names))
    for result in (manual, replace(original)):
        with pytest.raises(ValueError, match="no retained solve context"):
            compute_sectional_loads(result, **DEFINITION)
    with pytest.raises(TypeError, match="SolveResult"):
        compute_sectional_loads(object(), **DEFINITION)


@pytest.mark.parametrize(
    "changed",
    (
        "geometry",
        "local_loads",
        "attitude",
        "flow_state",
        "case_signature",
        "coefficients",
        "components",
    ),
)
def test_replacement_cannot_reuse_unrelated_solve_context(changed):
    original = _solve("fmf")
    other = _solve("hypersonic")
    substituted = replace(original, **{changed: getattr(other, changed)})
    with pytest.raises(ValueError, match="no retained solve context"):
        compute_sectional_loads(substituted, **DEFINITION)


def test_inputs_and_returned_arrays_are_immutable_without_caller_aliases():
    origin = np.array([0.2, -0.1, 0.4])
    direction = [0.2, 0.9, 0.4]
    component_ids = [1, 0]
    result = _solve("fmf")
    loads = compute_sectional_loads(
        result,
        axis_origin_stl_m=origin,
        axis_direction_stl=direction,
        bin_count=5,
        component_ids=component_ids,
    )
    origin[:] = 20
    direction[:] = [0, 0, 0]
    component_ids.clear()
    np.testing.assert_array_equal(loads.spec.axis_origin_stl_m, (0.2, -0.1, 0.4))
    np.testing.assert_array_equal(
        loads.spec.definition.axis_direction_stl, (0.2, 0.9, 0.4)
    )
    assert loads.spec.selected_component_ids == (0, 1)
    for retained in (loads, deepcopy(loads), pickle.loads(pickle.dumps(loads))):
        for array in _arrays(retained):
            assert not array.flags.writeable
            with pytest.raises(ValueError):
                array.setflags(write=True)
        for distribution in (
            retained.total,
            *(item.distribution for item in retained.components),
        ):
            for name in ("CA", "CY", "CN", "CD", "CL", "Cl", "Cm", "Cn"):
                with pytest.raises(ValueError):
                    getattr(distribution, name).setflags(write=True)
        with pytest.raises(FrozenInstanceError):
            retained.case_signature = "changed"
    # A round trip preserves the matching solve context without restoring I/O.
    restored = compute_sectional_loads(pickle.loads(pickle.dumps(result)), **DEFINITION)
    assert restored.case_signature == result.case_signature
    copied = deepcopy(result)
    assert copied is result
    for array in _arrays(copied):
        assert not array.flags.writeable
    assert (
        compute_sectional_loads(copied, **DEFINITION).case_signature
        == result.case_signature
    )


@pytest.mark.parametrize(
    "invalid",
    (
        {"axis_origin_stl_m": (True, 0, 0)},
        {"axis_direction_stl": (0, 0, 0)},
        {"axis_direction_stl": (1, np.inf, 0)},
        {"bin_count": 5.0},
        {"bin_count": True},
        {"start_m": 0.0},
        {"component_ids": (2,)},
        {"component_ids": ()},
    ),
)
def test_public_wrapper_preserves_a1_validation(invalid):
    with pytest.raises((TypeError, ValueError)):
        compute_sectional_loads(_solve("fmf"), **(DEFINITION | invalid))


def test_keyword_only_contract_and_empty_range():
    parameters = inspect.signature(compute_sectional_loads).parameters
    for name, parameter in list(parameters.items())[1:]:
        assert parameter.kind == inspect.Parameter.KEYWORD_ONLY
        if name in ("axis_origin_stl_m", "axis_direction_stl", "bin_count"):
            assert parameter.default == inspect.Parameter.empty
        else:
            assert parameter.default is None
    loads = compute_sectional_loads(
        _solve("hypersonic"), **DEFINITION, start_m=10, stop_m=20
    )
    assert not loads.spec.covers_selected_geometry
    for distribution in (
        loads.total,
        *(item.distribution for item in loads.components),
    ):
        for array in _arrays(distribution):
            assert np.count_nonzero(array) == 0


def test_documented_sectional_example_runs_for_both_domains():
    documentation = Path(__file__).parents[2] / "docs/running/python-api.md"
    example = re.search(
        r"<!-- python-api-sectional-example -->\s*```python\n(.*?)```",
        documentation.read_text(encoding="utf-8"),
        flags=re.DOTALL,
    )
    assert example is not None
    for domain in ("fmf", "hypersonic"):
        namespace = {"result": _solve(domain)}
        exec(compile(example[1], "python-api:sectional", "exec"), namespace)  # noqa: S102
        assert isinstance(namespace["loads"], SectionalLoads)
