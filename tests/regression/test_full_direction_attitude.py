"""User-approved full-direction contract, including serialized pole cases."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import pyvista as pv

from panelsolver import (
    FMFCase,
    HypersonicCase,
    resolve_attitude,
    solve_fmf,
    solve_hypersonic,
)
from panelsolver.app.runtime import run_and_write_product_cases
from panelsolver.domains import fmf, hypersonic

ROOT = Path(__file__).parents[2]
DIRECTION_FIELDS = tuple(f"velocity_hat_{axis}_stl" for axis in "xyz")
REMOVED_FIELDS = {
    "alpha_t_deg_resolved",
    "beta_t_deg_resolved",
    "alpha_stability_source",
    "beta_s_deg_resolved",
}


@pytest.mark.parametrize("domain", [fmf, hypersonic], ids=["fmf", "hypersonic"])
def test_csv_and_vtp_preserve_inputs_and_evaluated_state(domain, tmp_path):
    name = domain.__name__.rsplit(".", 1)[1]
    base = (
        domain.read_cases(ROOT / "examples" / name / "attitude_modes.csv")
        .iloc[0]
        .to_dict()
    )
    inputs = [
        (None, 60, 30),
        ("", 90, 90),
        ("   ", 60, 30),
        ("beta_tan", 460, 30),
        ("beta_sin", -260, 30),
        ("bank", 460, 390),
        ("beta_tan", 90, 30),
        ("beta_sin", 42, 90),
        ("beta_tan", 42, 90),
        ("bank", 90, 90),
    ]
    rows = [
        {
            **base,
            "case_id": f"direction-{i}",
            "alpha_deg": alpha,
            "beta_or_bank_deg": beta,
            "attitude_input": mode,
            "save_vtp_on": 1,
            "out_dir": str(tmp_path),
        }
        for i, (mode, alpha, beta) in enumerate(inputs)
    ]
    input_file = tmp_path / "input.csv"
    pd.DataFrame(rows).to_csv(input_file, index=False)
    loaded = domain.read_cases(input_file)
    # The GUI uses the same validated adapter; no screen rendering is required.
    gui_rows = domain.GUI_ADAPTERS.read_cases(input_file)
    assert len(gui_rows) == len(rows)
    output_file = tmp_path / "summary.csv"
    batch = run_and_write_product_cases(
        loaded.to_dict(orient="records"), domain.RUNTIME_POLICY, output_file
    )
    assert batch.summary_csv_saved
    assert not batch.output_issues
    csv = pd.read_csv(output_file, float_precision="round_trip")
    assert REMOVED_FIELDS.isdisjoint(csv.columns)
    for row in csv.to_dict(orient="records"):
        original = rows[int(row["case_id"].split("-")[-1])]
        attitude = resolve_attitude(
            original["alpha_deg"],
            original["beta_or_bank_deg"],
            original["attitude_input"],
        )
        assert row["out_attitude_input"] == attitude.input_mode
        assert row["alpha_deg"] == original["alpha_deg"]
        assert row["beta_or_bank_deg"] == original["beta_or_bank_deg"]
        np.testing.assert_allclose(
            [row[key] for key in DIRECTION_FIELDS],
            attitude.velocity_hat_stl,
            atol=1e-15,
            rtol=0,
        )
        assert row["alpha_stability_deg"] == pytest.approx(
            attitude.alpha_stability_deg, abs=1e-12
        )
        poly = pv.read(tmp_path / f"{row['case_id']}.vtp")
        assert REMOVED_FIELDS.isdisjoint(poly.field_data)
        assert poly.field_data["attitude_input_used"][0] == attitude.input_mode
        for key in (
            *DIRECTION_FIELDS,
            "alpha_stability_deg",
            "alpha_deg",
            "beta_or_bank_deg",
        ):
            assert poly.field_data[key].shape == (1,)
            assert poly.field_data[key].dtype == np.float64
            assert poly.field_data[key][0] == pytest.approx(row[key], abs=1e-15)
        assert poly.field_data["case_signature"][0] == row["case_signature"]
        assert np.isfinite(
            [row[key] for key in ("CA", "CY", "CN", "CD", "CL", "Cl", "Cm", "Cn")]
        ).all()


@pytest.mark.parametrize("domain", ["fmf", "hypersonic"])
@pytest.mark.parametrize("shielding", [False, True])
def test_equivalent_modes_have_the_same_loads_and_stability_axes(domain, shielding):
    common = {
        "case_id": "equivalent",
        "stl_paths": (ROOT / "examples/geometry/plate.stl",),
        "stl_scale_m_per_unit": 1,
        "Aref_m2": 1,
        "moment_reference_stl_m": (0, 0, 0),
        "Lref_Cl_m": 1,
        "Lref_Cm_m": 1,
        "Lref_Cn_m": 1,
        "shielding": shielding,
        "ray_backend": "rtree",
    }
    if domain == "fmf":
        make_case, solve = FMFCase, solve_fmf
        common.update(
            speed_ratio=7, translational_temperature_k=1000, wall_temperature_k=300
        )
    else:
        make_case, solve = HypersonicCase, solve_hypersonic
        common.update(mach=6, gamma=1.4)
    for alpha, beta in ((100, 30), (-100, -30), (180, 0), (90, 30), (42, 90)):
        sine = resolve_attitude(alpha, beta, "beta_sin")
        x, y, z = sine.velocity_hat_stl
        included = math.degrees(math.atan2(math.hypot(y, z), x))
        bank = math.degrees(math.atan2(-y, z))
        variants = [sine, resolve_attitude(included, bank, "bank")]
        if x != 0:
            tangent = math.degrees(math.atan2(-y, abs(x)))
            variants.append(resolve_attitude(alpha, tangent, "beta_tan"))
        elif z == 0:
            variants.append(resolve_attitude(42, beta, "beta_tan"))
        results = [
            solve(make_case(**common, attitude=attitude)) for attitude in variants
        ]
        for result in results:
            assert result.attitude.alpha_stability_deg == pytest.approx(
                sine.alpha_stability_deg, abs=1e-12
            )
            np.testing.assert_allclose(
                result.local_loads.traction_coeff_stl,
                results[0].local_loads.traction_coeff_stl,
                atol=1e-12,
                rtol=1e-12,
            )
            np.testing.assert_allclose(
                result.coefficients.force_coeff_stability,
                results[0].coefficients.force_coeff_stability,
                atol=1e-12,
                rtol=1e-12,
            )


@pytest.mark.parametrize("domain", [fmf, hypersonic], ids=["fmf", "hypersonic"])
@pytest.mark.parametrize("angles", [(60, 30), (90, 90)])
@pytest.mark.parametrize("mode", [None, "", "   "])
def test_default_mode_matches_explicit_sine_across_entrypoints(
    domain, angles, mode, tmp_path
):
    name = domain.__name__.rsplit(".", 1)[1]
    row = (
        domain.read_cases(ROOT / "examples" / name / "attitude_modes.csv")
        .iloc[0]
        .to_dict()
    )
    row.update(alpha_deg=angles[0], beta_or_bank_deg=angles[1])
    row.pop("attitude_input")
    if mode is not None:
        row["attitude_input"] = mode
    input_file = tmp_path / "default.csv"
    pd.DataFrame([row]).to_csv(input_file, index=False)
    expected = resolve_attitude(*angles, "beta_sin")
    np.testing.assert_array_equal(
        resolve_attitude(*angles).velocity_hat_stl, expected.velocity_hat_stl
    )
    np.testing.assert_array_equal(
        resolve_attitude(*angles, mode).velocity_hat_stl, expected.velocity_hat_stl
    )
    explicit = {**row, "attitude_input": "beta_sin"}
    assert domain.format_case(row) == domain.format_case(explicit)
    for loaded in (
        domain.read_cases(input_file).iloc[0].to_dict(),
        domain.GUI_ADAPTERS.read_cases(input_file)[0],
    ):
        assert loaded["attitude_input"] == "beta_sin"
        actual = domain.adapt_row(loaded).attitude
        np.testing.assert_array_equal(
            actual.velocity_hat_stl, expected.velocity_hat_stl
        )
        assert actual.alpha_stability_deg == expected.alpha_stability_deg
    if angles == (60, 30):
        assert not np.allclose(
            expected.velocity_hat_stl,
            resolve_attitude(*angles, "beta_tan").velocity_hat_stl,
        )
