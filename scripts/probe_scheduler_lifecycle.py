"""Bounded cross-platform probe for spawn startup and cleanup regressions."""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from panelsolver.core import (
    PartialResultPolicy,
    WorkerExecutionError,
    WorkerLogPolicy,
    WorkerStartupError,
    WorkerUnexpectedExitError,
    iter_case_results_parallel,
)


def _unexpected_exit_worker(case: int, _logfn) -> int:
    if case == 0:
        os._exit(7)
    time.sleep(0.05)
    return case


def _unpickleable_worker(_case: int, _logfn):
    return lambda: None


def _stubborn_worker(case: tuple[str, str], _logfn) -> int:
    behavior, marker_text = case
    marker = Path(marker_text)
    if behavior == "block":
        if os.name != "nt":
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        marker.touch()
        while True:
            time.sleep(0.05)
    deadline = time.monotonic() + 5.0
    while not marker.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("blocking worker did not become ready")
        time.sleep(0.01)
    return 1


def _resource_state() -> tuple[set[int], set[int]]:
    processes = {
        int(process.pid) for process in mp.active_children() if process.pid is not None
    }
    feeders = {
        int(thread.ident)
        for thread in threading.enumerate()
        if thread.name == "QueueFeederThread" and thread.ident is not None
    }
    return processes, feeders


def _assert_resources_released(
    baseline: tuple[set[int], set[int]],
    iteration: str,
) -> None:
    deadline = time.monotonic() + 2.0
    while _resource_state() != baseline and time.monotonic() < deadline:
        time.sleep(0.02)
    if _resource_state() != baseline:
        raise RuntimeError(
            f"{iteration} leaked worker resources: "
            f"baseline={baseline}, current={_resource_state()}"
        )


def _run_child(iterations: int) -> int:
    baseline = _resource_state()
    for iteration in range(iterations):
        try:
            list(
                iter_case_results_parallel(
                    (0, 1),
                    2,
                    _unexpected_exit_worker,
                    log_policy=WorkerLogPolicy.DROP,
                    partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                    chunk_cases=1,
                )
            )
        except WorkerUnexpectedExitError as exc:
            if (0, 7) not in exc.exits:
                raise RuntimeError(
                    f"iteration {iteration} lost the expected worker exit: {exc.exits}"
                ) from exc
        else:
            raise RuntimeError(
                f"iteration {iteration} did not report the unexpected worker exit"
            )
        _assert_resources_released(baseline, f"unexpected-exit iteration {iteration}")

        try:
            list(
                iter_case_results_parallel(
                    (0, 1),
                    2,
                    _unpickleable_worker,
                    log_policy=WorkerLogPolicy.DROP,
                    partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                    chunk_cases=1,
                )
            )
        except WorkerExecutionError as exc:
            if "serialize worker chunk_done" not in str(exc):
                raise
        else:
            raise RuntimeError(
                f"iteration {iteration} did not reject an unpickleable result"
            )
        _assert_resources_released(baseline, f"serialization iteration {iteration}")

        try:
            list(
                iter_case_results_parallel(
                    (0, 1),
                    2,
                    lambda case, _logfn: case,
                    log_policy=WorkerLogPolicy.DROP,
                    partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                    chunk_cases=1,
                )
            )
        except WorkerStartupError as exc:
            if "serialize spawn worker callable" not in str(exc):
                raise
        else:
            raise RuntimeError(
                f"iteration {iteration} accepted an unpickleable worker callable"
            )
        _assert_resources_released(baseline, f"startup iteration {iteration}")

    for iteration in range(min(iterations, 2)):
        with tempfile.TemporaryDirectory() as temp_dir:
            marker = str(Path(temp_dir) / "blocking-worker-ready")
            iterator = iter_case_results_parallel(
                (("block", marker), ("fast", marker)),
                2,
                _stubborn_worker,
                log_policy=WorkerLogPolicy.DROP,
                partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                bucket_keys=("block", "fast"),
                chunk_cases=1,
            )
            if next(iterator) != (1, 1):
                raise RuntimeError("early-close probe yielded the wrong result")
            iterator.close()
        _assert_resources_released(baseline, f"early-close iteration {iteration}")

    print(
        json.dumps(
            {
                "early_close_iterations": min(iterations, 2),
                "serialization_iterations": iterations,
                "startup_failure_iterations": iterations,
                "unexpected_exit_iterations": iterations,
                "resources": "clean",
            },
            sort_keys=True,
        )
    )
    return 0


def _kill_process_tree(process: subprocess.Popen[str]) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            capture_output=True,
            text=True,
        )
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _run_supervised(iterations: int, timeout_seconds: float) -> int:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        "--iterations",
        str(iterations),
    ]
    process_options: dict[str, object] = {}
    if os.name == "nt":
        process_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        process_options["start_new_session"] = True
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **process_options,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        _kill_process_tree(process)
        stdout, stderr = process.communicate()
        print(stdout, end="")
        print(stderr, file=sys.stderr, end="")
        print(
            f"scheduler lifecycle probe exceeded {timeout_seconds:.1f} seconds",
            file=sys.stderr,
        )
        return 1

    print(stdout, end="")
    if stderr:
        print(stderr, file=sys.stderr, end="")
    if process.returncode != 0:
        return int(process.returncode or 1)
    if stderr.strip():
        print("scheduler child wrote unexpected stderr", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be >= 1")
    if args.timeout_seconds <= 0.0:
        parser.error("--timeout-seconds must be > 0")
    if args.child:
        return _run_child(args.iterations)
    return _run_supervised(args.iterations, args.timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
