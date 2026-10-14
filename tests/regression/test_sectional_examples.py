"""Shared sphere-cone sectional definitions run cleanly in both domains."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from panelsolver.app import run_product_cases
from panelsolver.app.sectional_batch import run_sectional_cases
from panelsolver.app.sectional_definitions import read_sectional_definitions
from panelsolver.domains import fmf, hypersonic

EXAMPLES = Path(__file__).parents[2] / "examples"
DOMAINS = {"fmf": fmf, "hypersonic": hypersonic}
pytestmark = pytest.mark.slow


def _rows(domain, tmp_path):
    frame = DOMAINS[domain].read_cases(EXAMPLES / domain / "sphere_cone.csv")
    return tuple(
        {**row, "save_vtp_on": 0, "out_dir": str(tmp_path / "unused-vtp")}
        for row in frame.to_dict(orient="records")
    )


def _sectional_rows(domain, rows, *, cp):
    definitions = read_sectional_definitions(
        EXAMPLES / ("sectional_cp.csv" if cp else "sectional_loads.csv"), cp=cp
    )
    result = run_sectional_cases(rows, DOMAINS[domain].RUNTIME_POLICY, definitions)
    assert result.status == "completed"
    assert result.completed_pairs == len(rows) * len(definitions)
    return result.csv.rows


@pytest.mark.parametrize("domain", DOMAINS)
def test_sectional_loads_example_spans_sum_to_summary_totals(domain, tmp_path):
    rows = _rows(domain, tmp_path)
    totals = {
        row["case_id"]: row
        for row in run_product_cases(rows, DOMAINS[domain].RUNTIME_POLICY).csv.rows
        if row["scope"] == "total"
    }
    sectional = [
        row
        for row in _sectional_rows(domain, rows, cp=False)
        if row["scope"] == "total"
    ]
    coverage = {
        (row["section_id"], row["covers_selected_geometry"]) for row in sectional
    }
    assert coverage == {("axial", True), ("vertical", True), ("forebody", False)}
    for case_id, total in totals.items():
        for section_id in ("axial", "vertical"):
            bins = [
                row
                for row in sectional
                if row["case_id"] == case_id and row["section_id"] == section_id
            ]
            for name in ("CA", "CY", "CN", "Cl", "Cm", "Cn", "CD", "CL"):
                np.testing.assert_allclose(
                    sum(row[f"delta_{name}"] for row in bins),
                    total[name],
                    rtol=0,
                    atol=1e-12,
                    err_msg=f"{case_id}/{section_id}/{name}",
                )


@pytest.mark.parametrize("domain", DOMAINS)
def test_sectional_cp_example_planes_are_clean_and_windward_is_higher(domain, tmp_path):
    rows = _sectional_rows(domain, _rows(domain, tmp_path), cp=True)
    assert {row["plane_status"] for row in rows} == {"ok"}
    assert {row["omitted_segment_count"] for row in rows} == {0}
    for case_id in {row["case_id"] for row in rows} - {f"{domain}_sphere_cone_a00"}:
        station = [
            row
            for row in rows
            if row["case_id"] == case_id and row["section_id"] == "cone_station"
        ]
        windward = [row["scalar_value"] for row in station if row["z0_stl_m"] < 0]
        leeward = [row["scalar_value"] for row in station if row["z0_stl_m"] > 0]
        assert max(windward) > max(leeward), case_id
