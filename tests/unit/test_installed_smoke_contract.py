"""Keep installed-wheel expectations aligned with the approved output schema."""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import threading
from pathlib import Path

import numpy as np
import pytest

from panelsolver.domains import fmf, hypersonic

ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location(
    "installed_smoke", ROOT / "scripts/smoke_installed_wheel.py"
)
assert SPEC is not None and SPEC.loader is not None
SMOKE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SMOKE)


@pytest.mark.parametrize("jobs", [1, 2])
def test_release_examples_keep_all_commands_and_isolate_writes(
    tmp_path, monkeypatch, jobs
):
    archive = tmp_path / "source"
    archive.mkdir()
    (archive / "unchanged.txt").write_text("release archive")
    staging = tmp_path / "staging"
    staging.mkdir()
    calls = []
    barrier = threading.Barrier(jobs)

    def run(command, **kwargs):
        barrier.wait(timeout=30)
        work = kwargs["cwd"]
        assert (work / "unchanged.txt").read_text() == "release archive"
        (work / "same-output.txt").write_text("private result")
        assert kwargs["env"]["EXPERIMENT_SENTINEL"] == "preserved"
        assert command[-4:] == ["--workers", "1", "--checkpoint-every-cases", "0"]
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(SMOKE.subprocess, "run", run)
    SMOKE._smoke_release_examples(
        archive, staging, {"EXPERIMENT_SENTINEL": "preserved"}, jobs=jobs
    )
    expected = {
        ("fmf", "basic.csv"),
        ("fmf", "flow_modes.csv"),
        ("fmf", "attitude_modes.csv"),
        ("fmf", "shielding.csv"),
        ("hypersonic", "basic.csv"),
        ("hypersonic", "pressure_models.csv"),
        ("hypersonic", "attitude_modes.csv"),
        ("hypersonic", "shielding.csv"),
    }
    assert {(command[1], command[3].name) for command, _ in calls} == expected
    assert len(calls) == len({kwargs["cwd"] for _, kwargs in calls}) == 8
    assert len({kwargs["env"]["XDG_CACHE_HOME"] for _, kwargs in calls}) == jobs
    assert not (archive / "same-output.txt").exists()


def test_parallel_release_example_failure_is_not_lost(tmp_path, monkeypatch):
    archive = tmp_path / "source"
    archive.mkdir()
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        failed = command[1] == "fmf" and command[3].name == "basic.csv"
        return subprocess.CompletedProcess(command, 7 if failed else 0, "", "sentinel")

    monkeypatch.setattr(SMOKE.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="release example failed: fmf/basic.csv"):
        SMOKE._smoke_release_examples(archive, tmp_path, {}, jobs=2)
    assert len(calls) == 8


@pytest.mark.parametrize("jobs", [1, 2])
def test_help_batch_keeps_every_result_including_failure(tmp_path, monkeypatch, jobs):
    calls = []
    barrier = threading.Barrier(jobs)

    def run(command, **kwargs):
        barrier.wait(timeout=30)
        calls.append(kwargs)
        return subprocess.CompletedProcess(command, 7, "stdout", "stderr")

    monkeypatch.setattr(SMOKE.subprocess, "run", run)
    results = SMOKE._run_help_commands(
        Path("cli"), Path("gui"), tmp_path, {}, jobs=jobs
    )
    assert set(results) == {
        (command, *args)
        for command in (Path("cli"), Path("gui"))
        for args in (("--help",), ("fmf", "--help"), ("hypersonic", "--help"))
    }
    assert all(
        result.returncode == 7 and result.stderr == "stderr"
        for result in results.values()
    )
    assert len(calls) == len({call["cwd"] for call in calls}) == 6
    assert len({call["env"]["XDG_CACHE_HOME"] for call in calls}) == jobs


@pytest.mark.parametrize(
    "product,domain", [("fmfsolver", fmf), ("newtsolver", hypersonic)]
)
def test_installed_schema_migration_preserves_frozen_numerical_evidence(
    product, domain
):
    directory = ROOT / "tests/fixtures/phase1/golden" / product
    contract = json.loads((directory / "contracts.json").read_text())
    expected_columns = SMOKE._current_expected_columns(
        contract["cli_run"]["result_csv_columns"]
    )
    result_columns = list(domain.CSV_PROJECTION_POLICY.result_columns)
    assert expected_columns[-len(result_columns) :] == result_columns
    removed = {
        "alpha_t_deg_resolved",
        "beta_t_deg_resolved",
        "alpha_stability_source",
        "beta_s_deg_resolved",
    }
    for path in directory.glob("*.json"):
        if path.name == "contracts.json":
            continue
        golden = json.loads(path.read_text())
        original = copy.deepcopy(golden)
        rows = SMOKE._current_expected_csv_rows(golden)
        vtp = SMOKE._current_expected_vtp(product, golden)
        assert golden == original
        assert removed.isdisjoint(vtp["field_data"])
        for actual, historical in zip(rows, golden["csv"]["rows"], strict=True):
            assert set(actual) == set(expected_columns)
            for coefficient in ("CA", "CY", "CN", "CD", "CL", "Cl", "Cm", "Cn"):
                assert actual[coefficient] == historical[coefficient]
            for axis, value in zip(
                "xyz", golden["npz"]["arrays"]["Vhat_stl"]["values"], strict=True
            ):
                field = f"velocity_hat_{axis}_stl"
                assert actual[field] == value
                assert vtp["field_data"][field]["values"] == [value]
        for field in ("alpha_deg", "beta_or_bank_deg"):
            assert vtp["field_data"][field]["values"] == [
                golden["normalized_input"][field]
            ]
        np.testing.assert_array_equal(
            vtp["cell_data"]["C_face_stl"]["values"],
            golden["vtp"]["cell_data"]["C_face_stl"]["values"],
        )
