"""Subprocess entry for real CLI and spawn-worker SIGINT regression tests."""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
from pathlib import Path

from panelsolver.app import sectional_batch
from panelsolver.cli import main


def _signal_probe_case(prepared, logfn):
    directory = Path(os.environ["SECTIONAL_SIGINT_PROBE_DIRECTORY"])
    case_id = prepared.physical.adapted.request.common_case.case_id
    (directory / f"{case_id}.started").write_text("started")
    if os.environ.get("SECTIONAL_SIGINT_SELF_SIGNAL") == "1":
        # Works on Windows as well as POSIX; no parent-only signal simulation.
        signal.raise_signal(signal.SIGINT)
    deadline = time.monotonic() + 20
    while not (directory / "release").exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("test did not release the in-flight case")
        time.sleep(0.01)
    result = sectional_batch._run_sectional_case(prepared, logfn)
    (directory / f"{case_id}.finished").write_text("finished")
    return result


def _request_parent_cancellation(directory: Path) -> None:
    deadline = time.monotonic() + 20
    while len(tuple(directory.glob("*.started"))) < 2:
        if time.monotonic() >= deadline:
            return
        time.sleep(0.01)
    signal.raise_signal(signal.SIGINT)
    (directory / "cancel-requested").write_text("requested")


if __name__ == "__main__":
    sectional_batch._parallel_sectional_case = _signal_probe_case
    if os.environ.get("SECTIONAL_SIGINT_SELF_SIGNAL") == "1":
        threading.Thread(
            target=_request_parent_cancellation,
            args=(Path(os.environ["SECTIONAL_SIGINT_PROBE_DIRECTORY"]),),
            daemon=True,
        ).start()
    raise SystemExit(main(sys.argv[1:]))
