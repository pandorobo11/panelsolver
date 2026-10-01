from __future__ import annotations

import csv
import pickle
from dataclasses import fields, is_dataclass
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from panelsolver import (
    FMFCase,
    HypersonicCase,
    resolve_attitude,
    solve_fmf,
    solve_hypersonic,
)
from panelsolver.app import sectional_batch as batch
from panelsolver.app.sectional_definitions import SectionalDefinition
from panelsolver.core import SchedulerCancelled, SchedulerError
from panelsolver.core.sectional import SectionalLoadDefinition
from panelsolver.domains import fmf, hypersonic
from panelsolver.postprocess import compute_sectional_loads

EXAMPLES = Path(__file__).parents[2] / "examples"
DOMAINS = {"fmf": fmf, "hypersonic": hypersonic}


def _rows(domain="fmf", count=1, *, components=1):
    base = DOMAINS[domain].read_cases(EXAMPLES / domain / "basic.csv").iloc[0].to_dict()
    return tuple(
        {
            **base,
            "case_id": f"case_{index}",
            "stl_path": ";".join([base["stl_path"]] * components),
            "Aref_m2": 2.7,
            "ref_x_m": 0.3,
            "ref_y_m": -0.2,
            "ref_z_m": 0.7,
            "Lref_Cl_m": 1.5,
            "Lref_Cm_m": 2.3,
            "Lref_Cn_m": 3.1,
            "save_vtp_on": 1,
        }
        for index in range(count)
    )


def _definition(section_id="001", *, direction=(0, 1, 0), **kwargs):
    return SectionalDefinition(
        section_id,
        SectionalLoadDefinition(
            axis_origin_stl_m=np.array((0.2, -0.1, 0.4)),
            axis_direction_stl=np.array(direction),
            bin_count=kwargs.pop("bin_count", 3),
            **kwargs,
        ),
    )


def _run(rows=None, definitions=None, domain="fmf", **kwargs):
    return batch.run_sectional_cases(
        _rows(domain) if rows is None else rows,
        DOMAINS[domain].RUNTIME_POLICY,
        (_definition(),) if definitions is None else definitions,
        **kwargs,
    )


def _public_result(domain, row):
    common = {
        "case_id": row["case_id"],
        "stl_paths": tuple(row["stl_path"].split(";")),
        "stl_scale_m_per_unit": row["stl_scale_m_per_unit"],
        "attitude": resolve_attitude(
            row["alpha_deg"], row["beta_or_bank_deg"], row["attitude_input"]
        ),
        "Aref_m2": row["Aref_m2"],
        "moment_reference_stl_m": (row["ref_x_m"], row["ref_y_m"], row["ref_z_m"]),
        "Lref_Cl_m": row["Lref_Cl_m"],
        "Lref_Cm_m": row["Lref_Cm_m"],
        "Lref_Cn_m": row["Lref_Cn_m"],
        "shielding": bool(row["shielding_on"]),
        "ray_backend": row["ray_backend"],
    }
    if domain == "fmf":
        return solve_fmf(
            FMFCase(
                **common,
                speed_ratio=row["S"],
                translational_temperature_k=row["Ti_K"],
                wall_temperature_k=row["Tw_K"],
            )
        )
    return solve_hypersonic(
        HypersonicCase(
            **common,
            mach=row["Mach"],
            gamma=row["gamma"],
            windward_equation=row["windward_eq"],
            leeward_equation=row["leeward_eq"],
        )
    )


def test_schema_is_fixed_and_contains_no_cumulative_or_density_fields():
    assert batch.SECTIONAL_CSV_COLUMNS == (
        "case_id",
        "case_signature",
        "section_id",
        "batch_status",
        "requested_pairs",
        "completed_pairs",
        "origin_x_stl_m",
        "origin_y_stl_m",
        "origin_z_stl_m",
        "direction_x_stl",
        "direction_y_stl",
        "direction_z_stl",
        "direction_hat_x_stl",
        "direction_hat_y_stl",
        "direction_hat_z_stl",
        "requested_component_ids",
        "selected_component_ids",
        "all_components_selected",
        "range_mode",
        "requested_start_m",
        "requested_stop_m",
        "resolved_start_m",
        "resolved_stop_m",
        "selected_geometry_min_m",
        "selected_geometry_max_m",
        "covers_selected_geometry",
        "bin_count",
        "Aref_m2",
        "ref_x_stl_m",
        "ref_y_stl_m",
        "ref_z_stl_m",
        "Lref_Cl_m",
        "Lref_Cm_m",
        "Lref_Cn_m",
        "alpha_stability_deg",
        "scope",
        "component_id",
        "bin_index",
        "bin_start_m",
        "bin_stop_m",
        "bin_center_m",
        "bin_width_m",
        "wetted_area_m2",
        "delta_force_coeff_x_stl",
        "delta_force_coeff_y_stl",
        "delta_force_coeff_z_stl",
        "delta_force_coeff_x_body",
        "delta_force_coeff_y_body",
        "delta_force_coeff_z_body",
        "delta_force_coeff_x_stability",
        "delta_force_coeff_y_stability",
        "delta_force_coeff_z_stability",
        "delta_moment_area_coeff_x_body_m",
        "delta_moment_area_coeff_y_body_m",
        "delta_moment_area_coeff_z_body_m",
        "delta_moment_coeff_x_body",
        "delta_moment_coeff_y_body",
        "delta_moment_coeff_z_body",
        "delta_CA",
        "delta_CY",
        "delta_CN",
        "delta_CD",
        "delta_CL",
        "delta_Cl",
        "delta_Cm",
        "delta_Cn",
    )


@pytest.mark.parametrize("domain", DOMAINS)
def test_matches_public_api_all_frames_references_and_identity(domain):
    rows = _rows(domain, components=2)
    definition = _definition(
        "oblique, α", direction=(0.2, 0.9, 0.4), component_ids=(1,)
    )
    result = _run(rows, (definition,), domain)
    solved = _public_result(domain, rows[0])
    numerical = definition.definition
    expected = compute_sectional_loads(
        solved,
        axis_origin_stl_m=numerical.axis_origin_stl_m,
        axis_direction_stl=numerical.axis_direction_stl,
        bin_count=numerical.bin_count,
        component_ids=numerical.component_ids,
    )
    assert result.status == "completed"
    assert result.completed_cases == result.total_cases == 1
    assert result.completed_pairs == result.requested_pairs == 1
    assert result.errors == ()
    assert result.csv is not None
    assert len(result.csv.rows) == 6  # both total and the single selected component
    for scope, distribution in (
        ("total", expected.total),
        ("component", expected.components[0].distribution),
    ):
        actual = [row for row in result.csv.rows if row["scope"] == scope]
        for frame in ("stl", "body", "stability"):
            np.testing.assert_array_equal(
                [
                    [row[f"delta_force_coeff_{axis}_{frame}"] for axis in "xyz"]
                    for row in actual
                ],
                getattr(distribution, f"force_coeff_{frame}"),
            )
        for prefix, suffix, name in (
            ("delta_moment_area_coeff", "body_m", "moment_area_coeff_body_m"),
            ("delta_moment_coeff", "body", "moment_coeff_body"),
        ):
            np.testing.assert_array_equal(
                [
                    [row[f"{prefix}_{axis}_{suffix}"] for axis in "xyz"]
                    for row in actual
                ],
                getattr(distribution, name),
            )
        for name in ("CA", "CY", "CN", "CD", "CL", "Cl", "Cm", "Cn"):
            np.testing.assert_array_equal(
                [row[f"delta_{name}"] for row in actual], getattr(distribution, name)
            )
        np.testing.assert_array_equal(
            [row["wetted_area_m2"] for row in actual], distribution.wetted_area_m2
        )
        for row in actual:
            assert row["case_signature"] == solved.case_signature
            assert row["section_id"] == "oblique, α"
            assert (
                row["requested_component_ids"] == row["selected_component_ids"] == "1"
            )
            assert row["all_components_selected"] is False
            assert row["Aref_m2"] == 2.7
            assert row["Lref_Cm_m"] == 2.3
            assert row["ref_z_stl_m"] == 0.7
            assert row["batch_status"] == "completed"


@pytest.mark.parametrize("domain", DOMAINS)
def test_one_solve_per_case_no_artifacts_or_retained_arrays(domain, tmp_path):
    rows = tuple(
        {**row, "out_dir": str(tmp_path / "unused")} for row in _rows(domain, 2)
    )
    definitions = tuple(_definition(name) for name in ("001", "second", "third"))
    with patch.object(batch, "execute_case", wraps=batch.execute_case) as execute:
        result = _run(rows, definitions, domain)
    assert execute.call_count == 2
    assert result.completed_pairs == 6
    assert not (tmp_path / "unused").exists()

    def inspect(value):
        assert not isinstance(value, np.ndarray)
        if is_dataclass(value):
            for field in fields(value):
                inspect(getattr(value, field.name))
        elif isinstance(value, (tuple, list)):
            for item in value:
                inspect(item)

    inspect(result)
    restored = pickle.loads(pickle.dumps(result))
    assert restored == result
    with pytest.raises(TypeError):
        result.csv.rows[0]["case_id"] = "changed"


def test_fmf_mode_b_reuses_domain_adaptation():
    rows = tuple(fmf.read_cases(EXAMPLES / "fmf/flow_modes.csv").to_dict("records"))
    requests = []
    execute_case = batch.execute_case

    def record(request, **kwargs):
        requests.append(request)
        return execute_case(request, **kwargs)

    with patch.object(batch, "execute_case", side_effect=record):
        result = _run(rows, (_definition(), _definition("other")))
    assert result.status == "completed"
    assert result.completed_pairs == 4
    assert len(requests) == 2
    assert requests[1].model_case.payload["Mach"] == 25
    assert requests[1].model_case.payload["Altitude_km"] == 100
    first = [row for row in result.csv.rows if row["case_id"] == "fmf_mode_a"]
    second = [row for row in result.csv.rows if row["case_id"] == "fmf_mode_b"]
    np.testing.assert_allclose(
        [row["delta_CA"] for row in first],
        [row["delta_CA"] for row in second],
        rtol=1e-12,
        atol=0,
    )


def test_ranges_are_per_case_and_explicit_empty_bins_are_successes():
    first, second = _rows(count=2)
    second["stl_scale_m_per_unit"] = 2.0
    definitions = (
        _definition("auto"),
        _definition("partial", start_m=-0.1, stop_m=0.2),
        _definition("empty", start_m=5, stop_m=6),
    )
    result = _run((first, second), definitions)
    assert result.status == "completed"
    assert result.completed_pairs == 6
    actual = {(row["case_id"], row["section_id"]): row for row in result.csv.rows}
    assert actual["case_0", "auto"]["resolved_start_m"] == -0.4
    assert actual["case_1", "auto"]["resolved_start_m"] == -0.9
    assert actual["case_0", "partial"]["resolved_start_m"] == -0.1
    assert actual["case_1", "partial"]["resolved_start_m"] == -0.1
    empty = [row for row in result.csv.rows if row["section_id"] == "empty"]
    assert len(empty) == 12
    for row in empty:
        assert row["covers_selected_geometry"] is False
        assert row["wetted_area_m2"] == 0
        assert all(
            row[name] == 0
            for name in batch.SECTIONAL_CSV_COLUMNS
            if name.startswith("delta_")
        )


def test_missing_component_is_failure_not_zero_and_keeps_successful_prefix():
    definitions = (
        _definition(),
        _definition("missing", component_ids=(9,)),
        _definition("later"),
    )
    with patch.object(batch, "execute_case", wraps=batch.execute_case) as execute:
        result = _run(_rows(count=2), definitions)
    assert execute.call_count == 1
    assert result.status == "failed"
    assert (result.completed_pairs, result.requested_pairs, result.completed_cases) == (
        1,
        6,
        0,
    )
    assert [(error.case_id, error.section_id) for error in result.errors] == [
        ("case_0", "missing")
    ]
    assert "absent from mesh" in result.errors[0].message
    assert {row["section_id"] for row in result.csv.rows} == {"001"}
    assert {row["batch_status"] for row in result.csv.rows} == {"failed"}
    assert {row["completed_pairs"] for row in result.csv.rows} == {1}
    assert {row["requested_pairs"] for row in result.csv.rows} == {6}


def test_physics_and_auto_range_failure_have_distinct_labels():
    with patch.object(
        batch, "execute_case", side_effect=RuntimeError("physical failure")
    ):
        physical = _run()
    assert physical.csv is None
    assert physical.status == "failed"
    assert physical.errors[0].section_id is None
    assert physical.errors[0].message == "physical failure"
    planar = _run(definitions=(_definition(direction=(1, 0, 0)),))
    assert planar.csv is None
    assert planar.errors[0].section_id == "001"
    assert "zero projected extent" in planar.errors[0].message


def test_all_rows_are_adapted_before_first_solve():
    first, second = _rows(count=2)
    second["Aref_m2"] = 0
    with patch.object(batch, "execute_case") as execute:
        result = _run((first, second))
    execute.assert_not_called()
    assert result.status == "failed"
    assert result.errors[0].case_id == "case_1"


def test_cancel_before_solve_and_between_definitions_retains_prefix():
    with patch.object(batch, "execute_case") as execute:
        empty = _run(cancel_cb=lambda: True)
    execute.assert_not_called()
    assert empty.status == "cancelled"
    assert empty.csv is None
    count = 0
    project = batch._project_pair

    def count_project(*args):
        nonlocal count
        result = project(*args)
        count += 1
        return result

    with (
        patch.object(batch, "_project_pair", side_effect=count_project),
        patch.object(batch, "execute_case", wraps=batch.execute_case) as execute,
    ):
        partial = _run(
            _rows(count=2),
            (_definition(), _definition("later")),
            cancel_cb=lambda: count > 0,
        )
    assert execute.call_count == 1
    assert partial.status == "cancelled"
    assert (
        partial.completed_pairs,
        partial.requested_pairs,
        partial.completed_cases,
    ) == (1, 4, 0)
    assert partial.errors == ()
    assert {row["batch_status"] for row in partial.csv.rows} == {"cancelled"}


def test_parallel_failure_drains_active_cases_and_preserves_failure_status():
    first = _rows(components=2)[0]
    second = {**_rows()[0], "case_id": "case_1"}
    drained = []

    def parallel(cases, workers, runner, **kwargs):
        try:
            yield 1, runner(cases[1], kwargs["logfn"])
            assert kwargs["cancel_cb"]() is True
            yield 0, runner(cases[0], kwargs["logfn"])
            drained.append(True)
            raise SchedulerCancelled("Stopped at a case boundary")
        except GeneratorExit:
            pytest.fail("active scheduler was closed instead of drained")

    with patch.object(batch, "iter_case_results_parallel", side_effect=parallel):
        result = _run(
            (first, second),
            (_definition(), _definition("part", component_ids=(1,))),
            workers=2,
        )
    assert drained == [True]
    assert result.status == "failed"
    assert result.completed_pairs == 3
    assert result.completed_cases == 1
    assert [(error.case_id, error.section_id) for error in result.errors] == [
        ("case_1", "part")
    ]
    ids = [row["case_id"] for row in result.csv.rows]
    assert ids == sorted(ids)


def test_parallel_cancel_keeps_inflight_success_and_cleanup_failure_is_visible():
    def parallel(cases, workers, runner, **kwargs):
        yield 1, runner(cases[1], kwargs["logfn"])
        error = SchedulerCancelled("cancelled")
        error.add_note("Worker cleanup failed: synthetic")
        raise error

    with patch.object(batch, "iter_case_results_parallel", side_effect=parallel):
        result = _run(_rows(count=2), workers=2)
    assert result.status == "failed"
    assert result.completed_pairs == 1
    assert "cleanup failed" in result.errors[0].message


def test_consumer_exception_keeps_primary_and_cleanup_diagnostics():
    def parallel(cases, workers, runner, **kwargs):
        try:
            yield 0, runner(cases[0], kwargs["logfn"])
        finally:
            raise SchedulerError("cleanup problem")

    def fail_progress(done, total):
        raise RuntimeError("progress problem")

    with patch.object(batch, "iter_case_results_parallel", side_effect=parallel):
        with pytest.raises(RuntimeError, match="progress problem") as caught:
            _run(_rows(count=2), workers=2, progress_cb=fail_progress)
    assert caught.value.__notes__ == ["cleanup problem"]


def test_save_failure_preserves_previous_file_and_retained_result_can_retry(tmp_path):
    result = _run(definitions=(_definition('001, "日本語"\nline'),))
    output = tmp_path / "result.csv"
    output.write_text("previous valid contents\n", encoding="utf-8")
    with patch(
        "panelsolver.app.csv_writer.os.replace", side_effect=OSError("save failed")
    ):
        with pytest.raises(OSError, match="save failed"):
            batch.write_sectional_csv(output, result, ())
    assert output.read_text() == "previous valid contents\n"
    with patch.object(batch, "execute_case") as execute:
        assert batch.write_sectional_csv(output, result, ()) == output
    execute.assert_not_called()
    with output.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert {row["section_id"] for row in rows} == {'001, "日本語"\nline'}
    assert len(rows) == 6
    assert not list(tmp_path.glob("*.tmp"))


def test_zero_success_does_not_replace_existing_output(tmp_path):
    output = tmp_path / "result.csv"
    output.write_bytes(b"old output")
    result = _run(cancel_cb=lambda: True)
    with pytest.raises(ValueError, match="No completed sectional results"):
        batch.write_sectional_csv(output, result, ())
    assert output.read_bytes() == b"old output"


def test_all_loaded_inputs_and_aliases_are_protected_on_every_export(tmp_path):
    case_path = tmp_path / "cases.csv"
    definition_path = tmp_path / "sectional.csv"
    selected = tmp_path / "selected.stl"
    unselected = tmp_path / "unselected.stl"
    for path in (case_path, definition_path, selected, unselected):
        path.write_bytes(b"input")
    source_link = tmp_path / "source-link.csv"
    source_link.symlink_to(definition_path)
    protected = batch.sectional_protected_paths(
        case_path,
        source_link,
        ({"stl_path": "selected.stl"}, {"stl_path": "unselected.stl"}),
    )
    assert all(
        path in protected
        for path in (case_path, definition_path, source_link, selected, unselected)
    )
    # A later source-link retarget must not unprotect the original input target.
    replacement = tmp_path / "replacement.csv"
    replacement.write_bytes(b"replacement input")
    source_link.unlink()
    source_link.symlink_to(replacement)
    alias = tmp_path / "hardlink.csv"
    alias.hardlink_to(unselected)
    symlink = tmp_path / "symlink.csv"
    symlink.symlink_to(selected)
    result = _run()
    for output in (
        case_path,
        definition_path,
        source_link,
        selected,
        unselected,
        replacement,
        alias,
        symlink,
        tmp_path / "CASES.CSV",
    ):
        with pytest.raises(ValueError, match="collision"):
            batch.write_sectional_csv(output, result, protected)
    assert unselected.read_bytes() == selected.read_bytes() == b"input"
