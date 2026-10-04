from __future__ import annotations

import csv
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
pytestmark = pytest.mark.slow


def _run_probe(tmp_path: Path, *, group_signal: bool) -> None:
    output = tmp_path / "result.csv"
    environment = {
        **os.environ,
        "SECTIONAL_SIGINT_PROBE_DIRECTORY": str(tmp_path),
        "SECTIONAL_SIGINT_SELF_SIGNAL": "0" if group_signal else "1",
    }
    command = [
        sys.executable,
        "-m",
        "tests.sectional_sigint_probe",
        "fmf",
        "sectional-loads",
        "-i",
        str(ROOT / "examples/fmf/flow_modes.csv"),
        "-d",
        str(ROOT / "examples/sectional_loads.csv"),
        "-o",
        str(output),
        "-j",
        "2",
        "--plain",
        "--debug",
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=group_signal,
    )
    try:
        deadline = time.monotonic() + 30
        while process.poll() is None:
            ready = (
                len(tuple(tmp_path.glob("*.started"))) == 2
                if group_signal
                else (tmp_path / "cancel-requested").exists()
            )
            if ready:
                if group_signal:
                    # A terminal Ctrl-C reaches the foreground process group,
                    # including spawn children, rather than just the parent.
                    os.killpg(process.pid, signal.SIGINT)
                break
            if time.monotonic() >= deadline:
                pytest.fail("spawn workers did not become ready for SIGINT")
            time.sleep(0.01)
        (tmp_path / "release").write_text("release")
        stdout, stderr = process.communicate(timeout=30)
    finally:
        (tmp_path / "release").write_text("release")
        if process.poll() is None:
            process.terminate()
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=10)

    assert process.returncode == 130, (stdout, stderr)
    assert "KeyboardInterrupt" not in stderr
    assert "Failed:" not in stderr
    assert "Cancelled: 6/6" in stderr
    assert sorted(path.stem for path in tmp_path.glob("*.finished")) == [
        "fmf_mode_a",
        "fmf_mode_b",
    ]
    with output.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 80
    assert {row["batch_status"] for row in rows} == {"cancelled"}
    assert len({(row["case_id"], row["section_id"]) for row in rows}) == 6
    assert list(dict.fromkeys(row["case_id"] for row in rows)) == [
        "fmf_mode_a",
        "fmf_mode_b",
    ]


@pytest.mark.parametrize(
    "group_signal",
    (False, True) if os.name == "posix" else (False,),
    ids=lambda grouped: "terminal-group" if grouped else "worker-and-parent",
)
def test_parallel_cli_sigint_preserves_inflight_results(tmp_path, group_signal):
    # POSIX has distinct worker-local and terminal process-group delivery.
    # Windows supports only the former; do not repeat that same probe twice.
    _run_probe(tmp_path, group_signal=group_signal)
