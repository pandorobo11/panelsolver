"""Keep installed-wheel expectations aligned with the approved output schema."""

from __future__ import annotations

import copy
import importlib.util
import json
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
