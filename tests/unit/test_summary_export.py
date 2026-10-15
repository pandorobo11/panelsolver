from pathlib import Path
from unittest.mock import patch

import pytest

from panelsolver.app.csv_writer import write_csv_atomic
from panelsolver.app.solver_spec import GuiRunRequest
from panelsolver.app.summary_export import (
    SummaryCsvSnapshot,
    summary_protected_paths,
    write_summary_snapshot,
)
from panelsolver.domains import fmf, hypersonic

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("domain", [fmf, hypersonic])
def test_real_gui_adapter_retains_exact_failed_csv_without_another_solve(
    domain, tmp_path
):
    source = ROOT / "examples" / domain.RUNTIME_POLICY.product_id / "basic.csv"
    rows = tuple(
        dict(row, save_vtp_on=0)
        for row in domain.gui_spec().adapters.read_cases(source)
    )
    attempted = []

    def fail(path, projection):
        attempted.append(projection)
        raise OSError("disk full")

    request = GuiRunRequest(
        rows,
        1,
        0,
        tmp_path / "failed.csv",
        tmp_path,
        lambda _: None,
        lambda *_: None,
        lambda: False,
    )
    with patch("panelsolver.app.runtime.write_csv_atomic", side_effect=fail):
        result = domain.gui_spec().adapters.run_cases(request)
    assert result.summary_csv_saved is False
    assert result.unsaved_summary_csv is attempted[0]
    snapshot = SummaryCsvSnapshot(
        result.unsaved_summary_csv,
        summary_protected_paths(source, rows),
        request.output_path,
        source.name,
        len(rows),
        False,
    )
    expected = tmp_path / "expected.csv"
    write_csv_atomic(expected, attempted[0])
    with patch(
        "panelsolver.app.runtime.execute_case",
        side_effect=AssertionError("must not solve"),
    ):
        write_summary_snapshot(tmp_path / "retry.csv", snapshot, ())
    assert (tmp_path / "retry.csv").read_bytes() == expected.read_bytes()
    successful = domain.gui_spec().adapters.run_cases(request)
    assert successful.summary_csv_saved is True
    assert successful.unsaved_summary_csv is None
