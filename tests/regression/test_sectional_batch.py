from __future__ import annotations

import multiprocessing
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from trimesh import ray as trimesh_ray

from panelsolver.app import sectional_batch as batch
from panelsolver.app.sectional_definitions import SectionalDefinition
from panelsolver.core.sectional import SectionalLoadDefinition
from panelsolver.domains import fmf, hypersonic

EXAMPLES = Path(__file__).parents[2] / "examples"
pytestmark = pytest.mark.slow
BACKENDS = ("rtree", "embree") if trimesh_ray.has_embree else ("rtree",)


def _definitions():
    return (
        SectionalDefinition(
            "001",
            SectionalLoadDefinition(np.zeros(3), np.array((0, 1, 0)), 4),
        ),
        SectionalDefinition(
            "oblique, 日本語",
            SectionalLoadDefinition(
                np.array((0.2, -0.1, 0.4)),
                np.array((0.2, 0.9, 0.4)),
                3,
                start_m=-0.2,
                stop_m=0.3,
            ),
        ),
        SectionalDefinition(
            "empty",
            SectionalLoadDefinition(
                np.zeros(3),
                np.array((0, 1, 0)),
                2,
                start_m=5,
                stop_m=6,
            ),
        ),
    )


@pytest.mark.parametrize("domain", (fmf, hypersonic), ids=("fmf", "hypersonic"))
def test_representative_32_case_batch_matches_spawn_and_input_order(domain):
    name = domain.RUNTIME_POLICY.product_id
    source = domain.read_cases(EXAMPLES / name / "components.csv").iloc[0].to_dict()
    rows = tuple(
        {
            **source,
            "case_id": f"case_{index:02d}",
            "alpha_deg": float((index * 7) % 25),
            "save_vtp_on": 0,
        }
        for index in range(32)
    )
    definitions = _definitions()
    serial = batch.run_sectional_cases(rows, domain.RUNTIME_POLICY, definitions)
    parallel = batch.run_sectional_cases(
        rows, domain.RUNTIME_POLICY, definitions, workers=2
    )
    assert serial.status == parallel.status == "completed"
    assert serial.completed_pairs == parallel.completed_pairs == 96
    assert serial.completed_cases == parallel.completed_cases == 32
    assert serial.csv == parallel.csv
    expected = [
        (row["case_id"], definition.section_id, scope, component, index)
        for row in rows
        for definition in definitions
        for scope, component in (("total", None), ("component", 0), ("component", 1))
        for index in range(definition.definition.bin_count)
    ]
    assert [
        (
            row["case_id"],
            row["section_id"],
            row["scope"],
            row["component_id"],
            row["bin_index"],
        )
        for row in parallel.csv.rows
    ] == expected


@pytest.mark.parametrize("domain", (fmf, hypersonic), ids=("fmf", "hypersonic"))
@pytest.mark.parametrize("backend", BACKENDS)
def test_shielded_strips_keep_area_and_scheduler_recovers_input_order(domain, backend):
    name = domain.RUNTIME_POLICY.product_id
    source = domain.read_cases(EXAMPLES / name / "shielding.csv").iloc[0].to_dict()
    rows = tuple(
        {
            **source,
            "case_id": f"case_{index}",
            "shielding_on": index % 2,
            "ray_backend": backend,
            "save_vtp_on": 0,
        }
        for index in range(4)
    )
    definitions = (
        SectionalDefinition(
            "axial", SectionalLoadDefinition(np.zeros(3), np.array((1, 0, 0)), 2)
        ),
    )
    serial = batch.run_sectional_cases(rows, domain.RUNTIME_POLICY, definitions)
    parallel = batch.run_sectional_cases(
        rows, domain.RUNTIME_POLICY, definitions, workers=2
    )
    assert serial.status == parallel.status == "completed"
    assert serial.csv == parallel.csv
    # Shielding-first execution has order (1, 3, 0, 2), but export is input ordered.
    assert list(dict.fromkeys(row["case_id"] for row in parallel.csv.rows)) == [
        "case_0",
        "case_1",
        "case_2",
        "case_3",
    ]
    totals = [row for row in parallel.csv.rows if row["scope"] == "total"]
    for row in totals:
        assert row["wetted_area_m2"] == 1
        if row["case_id"] in {"case_1", "case_3"} and row["bin_index"] == 1:
            assert all(
                row[name] == 0
                for name in batch.SECTIONAL_CSV_COLUMNS
                if name.startswith("delta_")
            )
        else:
            assert row["delta_CA"] > 0


def _slow_sectional_worker(prepared, logfn):
    """Spawn-importable probe: successful cleanup must wait beyond its 2 s grace."""
    root = Path(prepared.physical.row["probe_dir"])
    case_id = prepared.physical.row["case_id"]
    (root / f"{case_id}.started").write_text("started")
    if case_id == "fast_failure":
        deadline = time.monotonic() + 10
        while not (root / "slow_success.started").exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("second worker did not start")
            time.sleep(0.01)
    else:
        time.sleep(2.6)
    result = batch._run_sectional_case(prepared, logfn)
    (root / f"{case_id}.finished").write_text(
        result.errors[0].message if result.errors else "success"
    )
    return result


def _probe_rows(tmp_path, *, fail):
    base = fmf.read_cases(EXAMPLES / "fmf/basic.csv").iloc[0].to_dict()
    first = {
        **base,
        "case_id": "fast_failure" if fail else "slow_first",
        "probe_dir": str(tmp_path),
        "save_vtp_on": 0,
    }
    second = {
        **base,
        "case_id": "slow_success",
        "probe_dir": str(tmp_path),
        "save_vtp_on": 0,
        "stl_path": f"{base['stl_path']};{base['stl_path']}",
    }
    return first, second


def test_real_spawn_cancellation_drains_slow_case_without_termination(tmp_path):
    initial_children = {process.pid for process in multiprocessing.active_children()}
    rows = _probe_rows(tmp_path, fail=False)
    with patch.object(batch, "_parallel_sectional_case", _slow_sectional_worker):
        result = batch.run_sectional_cases(
            rows,
            fmf.RUNTIME_POLICY,
            _definitions(),
            workers=2,
            cancel_cb=lambda: (tmp_path / "slow_success.started").exists(),
        )
    assert result.status == "cancelled"
    assert result.completed_pairs == 6
    assert result.completed_cases == 2
    assert result.errors == ()
    assert (tmp_path / "slow_first.finished").read_text() == "success"
    assert (tmp_path / "slow_success.finished").read_text() == "success"
    assert {
        process.pid for process in multiprocessing.active_children()
    } == initial_children
    assert {row["batch_status"] for row in result.csv.rows} == {"cancelled"}


def test_real_spawn_failure_drains_slow_success_and_keeps_partial_identity(tmp_path):
    initial_children = {process.pid for process in multiprocessing.active_children()}
    rows = _probe_rows(tmp_path, fail=True)
    definitions = (
        _definitions()[0],
        SectionalDefinition(
            "second-component",
            SectionalLoadDefinition(
                np.zeros(3),
                np.array((0, 1, 0)),
                2,
                component_ids=(1,),
            ),
        ),
    )
    with patch.object(batch, "_parallel_sectional_case", _slow_sectional_worker):
        result = batch.run_sectional_cases(
            rows, fmf.RUNTIME_POLICY, definitions, workers=2
        )
    assert result.status == "failed"
    assert result.completed_pairs == 3
    assert result.requested_pairs == 4
    assert result.completed_cases == 1
    assert [(error.case_id, error.section_id) for error in result.errors] == [
        ("fast_failure", "second-component")
    ]
    assert (tmp_path / "slow_success.finished").read_text() == "success"
    assert {
        process.pid for process in multiprocessing.active_children()
    } == initial_children
    assert {row["batch_status"] for row in result.csv.rows} == {"failed"}
