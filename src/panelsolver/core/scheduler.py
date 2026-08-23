"""Spawn-based, cache-aware scheduling for model-neutral case execution."""

from __future__ import annotations

import multiprocessing as mp
import sys
import time
import traceback
from collections import OrderedDict, deque
from collections.abc import Callable, Hashable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from multiprocessing.connection import wait as wait_connections

import numpy as np

from .errors import PanelSolverError
from .execution import (
    CaseExecutionRequest,
    CaseExecutionResult,
    SchedulingAffinityHint,
    case_execution_affinity_hints,
    execute_case,
)

_DEFAULT_CHUNK_CASES = 8
_POLL_SECONDS = 0.1
_CLEANUP_SECONDS = 2.0
_STARTUP_SECONDS = 30.0
_MAX_WORKER_AFFINITIES = 256


class SchedulerError(PanelSolverError, RuntimeError):
    """The shared scheduler could not complete its requested cases."""


class SchedulerCancelled(SchedulerError):
    """Cooperative cancellation stopped dispatch at a case boundary."""


class WorkerStartupError(SchedulerError):
    """A spawn worker could not be started."""


class WorkerExecutionError(SchedulerError):
    """A worker reported an exception with its remote traceback."""

    def __init__(
        self,
        worker_id: int,
        remote_error: str,
        remote_traceback: str,
    ) -> None:
        self.worker_id = worker_id
        self.remote_error = remote_error
        self.remote_traceback = remote_traceback
        detail = f"[WorkerError] worker {worker_id}: {remote_error}"
        if remote_traceback:
            detail = f"{detail}\n{remote_traceback}"
        super().__init__(detail)


class WorkerUnexpectedExitError(SchedulerError):
    """One or more busy workers exited without returning a message."""

    def __init__(self, exits: Sequence[tuple[int, int | None]]) -> None:
        self.exits = tuple((int(worker_id), exitcode) for worker_id, exitcode in exits)
        detail = ", ".join(
            f"worker {worker_id} (exit code {exitcode})"
            for worker_id, exitcode in self.exits
        )
        super().__init__(f"[WorkerError] {detail} exited without returning a result.")


class _WorkerConnectionClosed(Exception):
    """The parent closed its IPC endpoint during cancellation or cleanup."""


class WorkerLogPolicy(str, Enum):
    """Explicit preservation of the D015 dual logging contracts."""

    FORWARD = "forward"
    DROP = "drop"


class PartialResultPolicy(str, Enum):
    """Explicit preservation of legacy worker-failure partial-result behavior."""

    YIELD_COMPLETED = "yield_completed"
    DISCARD_CHUNK = "discard_chunk"


@dataclass(frozen=True, slots=True)
class SchedulerProgress:
    """Deterministic completion count emitted for one successful case."""

    case_index: int
    completed: int
    total: int


def _positive_integer(value: object, *, field: str) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise SchedulerError(f"{field} must be an integer >= 1.")
    try:
        if isinstance(value, (str, int, np.integer)):
            parsed = int(value)
        else:
            raise TypeError
    except (TypeError, ValueError, OverflowError) as exc:
        raise SchedulerError(f"{field} must be an integer >= 1.") from exc
    if parsed < 1:
        raise SchedulerError(f"{field} must be an integer >= 1.")
    return parsed


def resolve_parallel_chunk_cases(
    chunk_cases: int | None = None,
) -> int:
    """Validate an explicit product-neutral chunk size or return default 8."""
    return (
        _DEFAULT_CHUNK_CASES
        if chunk_cases is None
        else _positive_integer(chunk_cases, field="chunk_cases")
    )


def case_execution_bucket_keys(
    requests: Sequence[CaseExecutionRequest],
) -> tuple[Hashable, ...]:
    """Build scheduling hints without weakening any numerical cache identity."""
    keys: list[Hashable] = []
    for index, request in enumerate(requests):
        if not isinstance(request, CaseExecutionRequest):
            raise TypeError("requests must contain only CaseExecutionRequest instances")
        config = request.shielding
        if not config.enabled:
            keys.append(("single", index))
            continue
        keys.append(
            (
                "shield",
                request.stl_paths,
                request.scale_m_per_unit,
                request.mesh_validation_policy.value,
                tuple(float(value) for value in request.velocity_hat_stl),
                config.ray_backend.value,
                config.batch_size,
            )
        )
    return tuple(keys)


def reuse_oriented_execution_order(
    requests: Sequence[CaseExecutionRequest],
) -> tuple[int, ...]:
    """Group exact shielding-reuse buckets while preserving stable input order."""
    keys = case_execution_bucket_keys(requests)
    shielding_buckets: OrderedDict[Hashable, list[int]] = OrderedDict()
    unshielded: list[int] = []
    for index, key in enumerate(keys):
        if key[0] == "shield":
            shielding_buckets.setdefault(key, []).append(index)
        else:
            unshielded.append(index)
    return (
        *(index for indices in shielding_buckets.values() for index in indices),
        *unshielded,
    )


def ordered_success_snapshot[ResultT](
    completed: Mapping[int, ResultT],
    execution_order: Sequence[int],
) -> tuple[tuple[int, ResultT], ...]:
    """Return checkpoint-ready successful results in caller-defined input order."""
    return tuple(
        (int(index), completed[int(index)])
        for index in execution_order
        if int(index) in completed
    )


def _validated_execution_order(total: int, order: Sequence[int] | None) -> tuple[int, ...]:
    raw = tuple(range(total)) if order is None else tuple(order)
    normalized: list[int] = []
    for value in raw:
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
            raise SchedulerError("execution_order must contain integer indices.")
        index = int(value)
        if index < 0 or index >= total:
            raise SchedulerError("execution_order contains an out-of-range index.")
        normalized.append(index)
    if len(normalized) != total or len(set(normalized)) != total:
        raise SchedulerError("execution_order must contain every case index exactly once.")
    return tuple(normalized)


def _validated_bucket_keys(
    total: int,
    bucket_keys: Sequence[Hashable] | None,
) -> tuple[Hashable, ...]:
    keys: tuple[Hashable, ...]
    if bucket_keys is None:
        keys = tuple(("single", index) for index in range(total))
    else:
        keys = tuple(bucket_keys)
    if len(keys) != total:
        raise SchedulerError("bucket_keys must have one entry per case.")
    try:
        for key in keys:
            hash(key)
    except TypeError as exc:
        raise SchedulerError("bucket_keys entries must be hashable.") from exc
    return keys


def _validated_affinity_hints(
    total: int,
    affinity_hints: Sequence[Sequence[SchedulingAffinityHint]] | None,
) -> tuple[tuple[SchedulingAffinityHint, ...], ...]:
    if affinity_hints is None:
        return tuple(() for _ in range(total))
    if len(affinity_hints) != total:
        raise SchedulerError("affinity_hints must have one entry per case.")

    normalized: list[tuple[SchedulingAffinityHint, ...]] = []
    for case_hints in affinity_hints:
        try:
            raw = tuple(case_hints)
        except TypeError as exc:
            raise SchedulerError(
                "each affinity_hints entry must be an iterable of hints."
            ) from exc
        if not all(isinstance(hint, SchedulingAffinityHint) for hint in raw):
            raise SchedulerError(
                "affinity_hints entries must contain SchedulingAffinityHint instances."
            )
        deduplicated: OrderedDict[Hashable, SchedulingAffinityHint] = OrderedDict()
        for hint in raw:
            previous = deduplicated.get(hint.identity)
            if previous is None or hint.priority > previous.priority:
                deduplicated[hint.identity] = hint
        normalized.append(tuple(deduplicated.values()))
    return tuple(normalized)


def _build_bucket_chunks(
    execution_order: Sequence[int],
    bucket_keys: Sequence[Hashable],
    chunk_cases: int,
) -> tuple[
    dict[Hashable, deque[tuple[int, ...]]],
    dict[Hashable, int],
]:
    buckets: OrderedDict[Hashable, list[int]] = OrderedDict()
    for index in execution_order:
        buckets.setdefault(bucket_keys[index], []).append(index)

    chunks: dict[Hashable, deque[tuple[int, ...]]] = {}
    remaining: dict[Hashable, int] = {}
    for key, indices in buckets.items():
        chunks[key] = deque(
            tuple(indices[start : start + chunk_cases])
            for start in range(0, len(indices), chunk_cases)
        )
        remaining[key] = len(indices)
    return chunks, remaining


def _affinity_score(
    indices: Iterable[int],
    affinity_hints: Sequence[Sequence[SchedulingAffinityHint]],
    worker_affinities: Mapping[Hashable, None],
) -> tuple[tuple[int, int], ...]:
    """Return lexicographic hit counts, highest generic priority first."""
    hits_by_priority: dict[int, int] = {}
    for index in indices:
        for hint in affinity_hints[index]:
            if hint.identity in worker_affinities:
                hits_by_priority[hint.priority] = (
                    hits_by_priority.get(hint.priority, 0) + 1
                )
    return tuple(sorted(hits_by_priority.items(), reverse=True))


def _bucket_affinity_score(
    chunks: Sequence[Sequence[int]],
    affinity_hints: Sequence[Sequence[SchedulingAffinityHint]],
    worker_affinities: Mapping[Hashable, None],
) -> tuple[tuple[int, int], ...]:
    return _affinity_score(
        (index for chunk in chunks for index in chunk),
        affinity_hints,
        worker_affinities,
    )


def _record_worker_affinities(
    worker_affinities: OrderedDict[Hashable, None],
    completed_case_hints: Sequence[SchedulingAffinityHint],
) -> None:
    """Update bounded parent-side LRU evidence after successful execution."""
    for hint in completed_case_hints:
        worker_affinities.pop(hint.identity, None)
        worker_affinities[hint.identity] = None
    while len(worker_affinities) > _MAX_WORKER_AFFINITIES:
        worker_affinities.popitem(last=False)


def _pick_next_chunk(
    worker_id: int,
    worker_last_bucket: list[Hashable | None],
    worker_affinities: Sequence[OrderedDict[Hashable, None]],
    bucket_chunks: dict[Hashable, deque[tuple[int, ...]]],
    bucket_remaining: dict[Hashable, int],
    bucket_owner: dict[Hashable, int | None],
    bucket_order: Mapping[Hashable, int],
    affinity_hints: Sequence[Sequence[SchedulingAffinityHint]],
) -> tuple[Hashable, tuple[int, ...]] | None:
    last = worker_last_bucket[worker_id]
    if last is not None and bucket_chunks.get(last):
        # Primary locality is absolute: finish this worker's ray bucket first.
        bucket = last
    else:
        unowned = [
            key
            for key, chunks in bucket_chunks.items()
            if chunks and bucket_owner.get(key) is None
        ]
        if unowned:
            # Every unowned candidate is a new primary-cache miss for this
            # worker, so secondary affinity can choose among them before load.
            bucket = max(
                unowned,
                key=lambda key: (
                    _bucket_affinity_score(
                        bucket_chunks[key],
                        affinity_hints,
                        worker_affinities[worker_id],
                    ),
                    bucket_remaining[key],
                    -bucket_order[key],
                ),
            )
            bucket_owner[bucket] = worker_id
        elif bucket_chunks:
            # Stealing duplicates the primary ray work.  Remaining workload
            # therefore dominates model-cache affinity for owned buckets.
            bucket = max(
                bucket_chunks,
                key=lambda key: (
                    bucket_remaining[key],
                    _bucket_affinity_score(
                        bucket_chunks[key],
                        affinity_hints,
                        worker_affinities[worker_id],
                    ),
                    -bucket_order[key],
                ),
            )
        else:
            return None
        worker_last_bucket[worker_id] = bucket

    # Keep stable chunk order inside the selected primary bucket.  The same
    # worker already retains its process-local caches, and a repeated full scan
    # for a more affine chunk would make large buckets quadratic to dispatch.
    indices = bucket_chunks[bucket].popleft()
    bucket_remaining[bucket] -= len(indices)
    if bucket_remaining[bucket] == 0:
        bucket_chunks.pop(bucket)
        bucket_remaining.pop(bucket)
        bucket_owner.pop(bucket, None)
    return bucket, indices


def _null_log(_message: str) -> None:
    return None


def _exception_detail(exc: Exception) -> str:
    try:
        return str(exc)
    except Exception:
        return "<exception text unavailable>"


def _safe_exception_text(exc: Exception) -> str:
    return f"{type(exc).__name__}: {_exception_detail(exc)}"


def _encode_parent_message(message: Mapping[str, object]) -> memoryview:
    """Serialize tasks synchronously before sending one Pipe frame."""
    try:
        return mp.reduction.ForkingPickler.dumps(dict(message))
    except Exception as exc:
        raise SchedulerError(
            f"Could not serialize worker task: {_safe_exception_text(exc)}"
        ) from exc


def _validate_spawn_callable(run_case_fn: object) -> None:
    """Reject an unpickleable worker callable before any child is created."""
    try:
        mp.reduction.ForkingPickler.dumps(run_case_fn)
    except Exception as exc:
        raise WorkerStartupError(
            "Could not serialize spawn worker callable: "
            f"{_safe_exception_text(exc)}"
        ) from exc


def _encode_worker_message(message: Mapping[str, object]) -> memoryview:
    """Serialize before Pipe.send_bytes so failures are observable."""
    try:
        return mp.reduction.ForkingPickler.dumps(dict(message))
    except Exception as exc:
        message_type = str(message.get("type", "unknown"))
        worker_id = int(message.get("worker_id", -1))
        serialization_error = _safe_exception_text(exc)
        original_error = _exception_detail(message.get("error")) if isinstance(
            message.get("error"), Exception
        ) else str(message.get("error") or "")
        original_traceback = str(message.get("traceback") or "")
        if original_error:
            error = (
                f"{original_error}; additionally could not serialize worker "
                f"{message_type} message: {serialization_error}"
            )
        else:
            error = (
                f"Could not serialize worker {message_type} message: "
                f"{serialization_error}"
            )
        serialization_traceback = traceback.format_exc()
        combined_traceback = original_traceback
        if combined_traceback:
            combined_traceback += "\n\nDuring worker message serialization:\n"
        combined_traceback += serialization_traceback
        fallback = {
            "type": "error",
            "worker_id": worker_id,
            "error": error,
            "traceback": combined_traceback,
            "logs": (),
            "results": (),
        }
        return mp.reduction.ForkingPickler.dumps(fallback)


def _put_worker_message(
    result_connection: object,
    message: Mapping[str, object],
) -> None:
    try:
        result_connection.send_bytes(_encode_worker_message(message))
    except (BrokenPipeError, EOFError, OSError) as exc:
        raise _WorkerConnectionClosed from exc


def _decode_worker_message(payload: object) -> Mapping[str, object]:
    if not isinstance(payload, bytes):
        raise SchedulerError("worker returned a non-bytes message payload.")
    try:
        message = mp.reduction.ForkingPickler.loads(payload)
    except Exception as exc:
        raise SchedulerError(
            f"worker returned an undecodable message: {_safe_exception_text(exc)}"
        ) from exc
    if not isinstance(message, Mapping):
        raise SchedulerError("worker returned a non-mapping message.")
    return message


def _worker_loop[CaseT, ResultT](
    worker_id: int,
    task_connection: object,
    result_connection: object,
    cancel_event: object,
    run_case_fn: Callable[[CaseT, Callable[[str], None]], ResultT],
    capture_logs: bool,
    include_partial_results: bool,
) -> None:
    """Execute complete cases; cancellation is observed only between cases."""
    _put_worker_message(
        result_connection,
        {
            "type": "ready",
            "worker_id": worker_id,
        },
    )
    while True:
        try:
            task_payload = task_connection.recv_bytes()
        except (EOFError, OSError):
            return
        try:
            message = mp.reduction.ForkingPickler.loads(task_payload)
        except Exception as exc:
            _put_worker_message(
                result_connection,
                {
                    "type": "error",
                    "worker_id": worker_id,
                    "error": (
                        "Could not decode worker task: "
                        f"{_safe_exception_text(exc)}"
                    ),
                    "traceback": traceback.format_exc(),
                    "logs": (),
                    "results": (),
                },
            )
            return
        if not isinstance(message, Mapping):
            _put_worker_message(
                result_connection,
                {
                    "type": "error",
                    "worker_id": worker_id,
                    "error": "Worker task was not a mapping.",
                    "traceback": "",
                    "logs": (),
                    "results": (),
                },
            )
            return
        message_type = message.get("type")
        if message_type == "shutdown":
            return
        if message_type != "run_chunk":
            _put_worker_message(
                result_connection,
                {
                    "type": "error",
                    "worker_id": worker_id,
                    "error": f"Unknown task type: {message_type}",
                    "traceback": "",
                    "logs": (),
                    "results": (),
                }
            )
            return

        bucket = message.get("bucket")
        indices = tuple(message.get("indices") or ())
        cases = tuple(message.get("cases") or ())
        if len(indices) != len(cases):
            _put_worker_message(
                result_connection,
                {
                    "type": "error",
                    "worker_id": worker_id,
                    "bucket": bucket,
                    "error": "Task indices/cases size mismatch.",
                    "traceback": "",
                    "logs": (),
                    "results": (),
                }
            )
            return

        results: list[tuple[int, ResultT]] = []
        logs: list[str] = []
        logfn = logs.append if capture_logs else _null_log
        try:
            for index, case in zip(indices, cases, strict=True):
                if cancel_event.is_set():
                    break
                results.append((int(index), run_case_fn(case, logfn)))
        except Exception as exc:
            _put_worker_message(
                result_connection,
                {
                    "type": "error",
                    "worker_id": worker_id,
                    "bucket": bucket,
                    "error": _exception_detail(exc),
                    "traceback": traceback.format_exc(),
                    "logs": tuple(logs),
                    "results": tuple(results) if include_partial_results else (),
                }
            )
            return

        _put_worker_message(
            result_connection,
            {
                "type": "chunk_done",
                "worker_id": worker_id,
                "bucket": bucket,
                "canceled": bool(cancel_event.is_set()),
                "logs": tuple(logs),
                "results": tuple(results),
            }
        )


def _worker_process_entry[CaseT, ResultT](
    worker_id: int,
    task_connection: object,
    result_connection: object,
    cancel_event: object,
    run_case_fn: Callable[[CaseT, Callable[[str], None]], ResultT],
    capture_logs: bool,
    include_partial_results: bool,
) -> None:
    try:
        _worker_loop(
            worker_id,
            task_connection,
            result_connection,
            cancel_event,
            run_case_fn,
            capture_logs,
            include_partial_results,
        )
    except _WorkerConnectionClosed:
        return


def _cleanup_workers(
    cancel_event: object,
    task_connections: Sequence[object],
    result_connections: Sequence[object],
    child_connections: Sequence[object],
    started_processes: Sequence[mp.Process],
) -> tuple[str, ...]:
    errors: list[str] = []
    try:
        cancel_event.set()
    except Exception as exc:
        errors.append(f"could not set worker cancellation: {_safe_exception_text(exc)}")
    # Closing is non-blocking and wakes idle receivers with EOF.  A synchronous
    # shutdown frame could itself block while a busy worker is not reading.
    for task_connection in task_connections:
        try:
            task_connection.close()
        except Exception as exc:
            errors.append(
                f"worker task connection cleanup failed: {_safe_exception_text(exc)}"
            )
    for connection in (*result_connections, *child_connections):
        try:
            connection.close()
        except Exception as exc:
            errors.append(
                f"worker connection cleanup failed: {_safe_exception_text(exc)}"
            )

    def join_until_deadline() -> None:
        deadline = time.monotonic() + _CLEANUP_SECONDS
        for process in started_processes:
            try:
                if not process.is_alive():
                    process.join()
                    continue
                process.join(timeout=max(0.0, deadline - time.monotonic()))
            except Exception as exc:
                errors.append(
                    f"worker {process.pid} join failed: {_safe_exception_text(exc)}"
                )

    def alive_processes() -> list[mp.Process]:
        alive: list[mp.Process] = []
        for process in started_processes:
            try:
                if process.is_alive():
                    alive.append(process)
            except Exception as exc:
                errors.append(
                    f"worker {process.pid} liveness check failed: "
                    f"{_safe_exception_text(exc)}"
                )
        return alive

    join_until_deadline()
    for process in alive_processes():
        try:
            process.terminate()
        except Exception as exc:
            errors.append(
                f"worker {process.pid} terminate failed: {_safe_exception_text(exc)}"
            )
    join_until_deadline()
    for process in alive_processes():
        try:
            process.kill()
        except Exception as exc:
            errors.append(
                f"worker {process.pid} kill failed: {_safe_exception_text(exc)}"
            )
    join_until_deadline()

    survivors = alive_processes()
    if survivors:
        errors.append(
            "workers remained alive after kill: "
            + ", ".join(str(process.pid) for process in survivors)
        )
    for process in started_processes:
        if process in survivors:
            continue
        try:
            process.close()
        except Exception as exc:
            errors.append(
                f"worker {process.pid} close failed: {_safe_exception_text(exc)}"
            )

    return tuple(errors)


def _wait_for_worker_readiness(
    result_connections: Sequence[object],
    processes: Sequence[mp.Process],
    *,
    cancel_cb: Callable[[], bool] | None = None,
) -> None:
    ready: set[int] = set()
    deadline = time.monotonic() + _STARTUP_SECONDS
    while len(ready) < len(processes):
        if cancel_cb is not None and bool(cancel_cb()):
            raise SchedulerCancelled("Canceled by user at a case boundary.")
        remaining = deadline - time.monotonic()
        if remaining <= 0.0:
            missing = sorted(set(range(len(processes))) - ready)
            raise WorkerStartupError(
                f"Spawn workers did not become ready before timeout: {missing}."
            )
        readable = wait_connections(
            result_connections,
            timeout=min(_POLL_SECONDS, remaining),
        )
        if not readable:
            dead_workers: list[tuple[int, int | None]] = []
            for worker_id, process in enumerate(processes):
                if worker_id in ready or process.is_alive():
                    continue
                process.join(timeout=_CLEANUP_SECONDS)
                dead_workers.append((worker_id, process.exitcode))
            if dead_workers:
                raise WorkerUnexpectedExitError(dead_workers)
            continue
        connection = readable[0]
        expected_worker_id = result_connections.index(connection)
        unexpected_exit: WorkerUnexpectedExitError | None = None
        try:
            payload = connection.recv_bytes()
        except (EOFError, OSError) as exc:
            process = processes[expected_worker_id]
            process.join(timeout=_CLEANUP_SECONDS)
            if not process.is_alive() and process.exitcode is not None:
                unexpected_exit = WorkerUnexpectedExitError(
                    ((expected_worker_id, process.exitcode),)
                )
            else:
                raise WorkerStartupError(
                    f"Spawn worker {expected_worker_id} closed before reporting ready."
                ) from exc
        if unexpected_exit is not None:
            raise unexpected_exit
        try:
            message = _decode_worker_message(payload)
        except SchedulerError as exc:
            raise WorkerStartupError(str(exc)) from exc
        finally:
            del payload
        if message.get("type") != "ready":
            raise WorkerStartupError(
                f"Spawn worker returned {message.get('type')!r} before ready."
            )
        worker_id = int(message.get("worker_id", -1))
        if worker_id < 0 or worker_id >= len(processes):
            raise WorkerStartupError("Spawn worker returned an invalid worker_id.")
        if worker_id in ready:
            raise WorkerStartupError(
                f"Spawn worker {worker_id} returned duplicate ready messages."
            )
        if worker_id != expected_worker_id:
            raise WorkerStartupError(
                f"Spawn worker {expected_worker_id} reported worker_id {worker_id}."
            )
        ready.add(worker_id)


def iter_case_results_parallel[CaseT, ResultT](
    cases: Sequence[CaseT],
    workers: int,
    run_case_fn: Callable[[CaseT, Callable[[str], None]], ResultT],
    *,
    log_policy: WorkerLogPolicy | str,
    partial_result_policy: PartialResultPolicy | str,
    execution_order: Sequence[int] | None = None,
    bucket_keys: Sequence[Hashable] | None = None,
    affinity_hints: Sequence[Sequence[SchedulingAffinityHint]] | None = None,
    chunk_cases: int | None = None,
    cancel_cb: Callable[[], bool] | None = None,
    logfn: Callable[[str], None] | None = None,
    progress_cb: Callable[[SchedulerProgress], None] | None = None,
    snapshot_cb: Callable[[tuple[tuple[int, ResultT], ...]], None] | None = None,
) -> Iterator[tuple[int, ResultT]]:
    """Yield completion-order results from spawn workers.

    Final and checkpoint order is recovered with ``ordered_success_snapshot``.
    Primary bucket continuity always precedes optional, performance-only worker
    affinity hints.
    The two legacy log and failure-partial behaviors are required policy inputs,
    not silently normalized defaults.
    """
    records = tuple(cases)
    total = len(records)
    if total == 0:
        return
    worker_count = _positive_integer(workers, field="workers")
    if worker_count < 2 or total < 2:
        raise SchedulerError(
            "iter_case_results_parallel requires workers >= 2 and at least 2 cases."
        )
    worker_count = min(worker_count, total)
    if not callable(run_case_fn):
        raise TypeError("run_case_fn must be callable")
    try:
        selected_log_policy = WorkerLogPolicy(log_policy)
    except (TypeError, ValueError) as exc:
        raise SchedulerError("log_policy must be 'forward' or 'drop'.") from exc
    try:
        selected_partial_policy = PartialResultPolicy(partial_result_policy)
    except (TypeError, ValueError) as exc:
        raise SchedulerError(
            "partial_result_policy must be 'yield_completed' or 'discard_chunk'."
        ) from exc

    order = _validated_execution_order(total, execution_order)
    keys = _validated_bucket_keys(total, bucket_keys)
    hints = _validated_affinity_hints(total, affinity_hints)
    resolved_chunk_cases = resolve_parallel_chunk_cases(chunk_cases)
    bucket_chunks, bucket_remaining = _build_bucket_chunks(
        order,
        keys,
        resolved_chunk_cases,
    )
    bucket_owner: dict[Hashable, int | None] = {
        bucket: None for bucket in bucket_chunks
    }
    bucket_order = {
        bucket: position for position, bucket in enumerate(bucket_chunks)
    }
    worker_last_bucket: list[Hashable | None] = [None] * worker_count
    worker_affinities: list[OrderedDict[Hashable, None]] = [
        OrderedDict() for _ in range(worker_count)
    ]

    # On Windows, multiprocessing creates the child before it pickles the
    # process object.  Preflight the user callable so serialization failure
    # cannot leave a half-started child emitting a delayed bootstrap traceback.
    _validate_spawn_callable(run_case_fn)
    context = mp.get_context("spawn")
    cancel_event = context.Event()
    task_pairs = [context.Pipe(duplex=False) for _ in range(worker_count)]
    task_receivers = [pair[0] for pair in task_pairs]
    task_senders = [pair[1] for pair in task_pairs]
    result_pairs = [context.Pipe(duplex=False) for _ in range(worker_count)]
    result_receivers = [pair[0] for pair in result_pairs]
    result_senders = [pair[1] for pair in result_pairs]
    child_connections = (*task_receivers, *result_senders)
    processes = [
        context.Process(
            target=_worker_process_entry,
            args=(
                worker_id,
                task_receivers[worker_id],
                result_senders[worker_id],
                cancel_event,
                run_case_fn,
                selected_log_policy is WorkerLogPolicy.FORWARD,
                selected_partial_policy is PartialResultPolicy.YIELD_COMPLETED,
            ),
            daemon=True,
        )
        for worker_id in range(worker_count)
    ]
    worker_busy = [False] * worker_count
    started_processes: list[mp.Process] = []
    completed: dict[int, ResultT] = {}
    cancellation_requested = False

    def assign_next(worker_id: int) -> bool:
        picked = _pick_next_chunk(
            worker_id,
            worker_last_bucket,
            worker_affinities,
            bucket_chunks,
            bucket_remaining,
            bucket_owner,
            bucket_order,
            hints,
        )
        if picked is None:
            return False
        bucket, indices = picked
        try:
            task_senders[worker_id].send_bytes(
                _encode_parent_message(
                    {
                        "type": "run_chunk",
                        "bucket": bucket,
                        "indices": indices,
                        "cases": tuple(records[index] for index in indices),
                    }
                )
            )
        except SchedulerError:
            raise
        except Exception as exc:
            raise SchedulerError(
                f"Could not dispatch work to worker {worker_id}: "
                f"{_safe_exception_text(exc)}"
            ) from exc
        worker_busy[worker_id] = True
        return True

    def accept_result(
        worker_id: int,
        index: int,
        result: ResultT,
    ) -> tuple[int, ResultT]:
        if index in completed:
            raise SchedulerError(f"worker returned duplicate case index {index}.")
        _record_worker_affinities(worker_affinities[worker_id], hints[index])
        completed[index] = result
        if progress_cb is not None:
            progress_cb(SchedulerProgress(index, len(completed), total))
        if snapshot_cb is not None:
            snapshot_cb(ordered_success_snapshot(completed, order))
        return index, result

    try:
        try:
            for process in processes:
                process.start()
                started_processes.append(process)
        except Exception as exc:
            raise WorkerStartupError(f"Could not start spawn worker: {exc}") from exc

        _wait_for_worker_readiness(
            result_receivers,
            processes,
            cancel_cb=cancel_cb,
        )
        for connection in child_connections:
            connection.close()
        for worker_id in range(worker_count):
            assign_next(worker_id)

        while len(completed) < total:
            if (
                not cancellation_requested
                and cancel_cb is not None
                and bool(cancel_cb())
            ):
                cancellation_requested = True
                cancel_event.set()
            if cancellation_requested and not any(worker_busy):
                raise SchedulerCancelled("Canceled by user at a case boundary.")

            readable = wait_connections(result_receivers, timeout=_POLL_SECONDS)
            if not readable:
                dead_workers = [
                    (worker_id, processes[worker_id].exitcode)
                    for worker_id in range(worker_count)
                    if worker_busy[worker_id]
                    and not processes[worker_id].is_alive()
                ]
                if dead_workers:
                    cancel_event.set()
                    raise WorkerUnexpectedExitError(dead_workers)
                continue
            connection = readable[0]
            expected_worker_id = result_receivers.index(connection)
            try:
                payload = connection.recv_bytes()
            except (EOFError, OSError) as exc:
                process = processes[expected_worker_id]
                # EOF can become visible just before multiprocessing records the
                # child status.  Reap for a bounded interval so a real exit code
                # is not exposed as ``None`` merely because of that race.
                process.join(timeout=_CLEANUP_SECONDS)
                raise WorkerUnexpectedExitError(
                    ((expected_worker_id, process.exitcode),)
                ) from exc
            message = _decode_worker_message(payload)
            del payload

            worker_id = int(message.get("worker_id", -1))
            if worker_id < 0 or worker_id >= worker_count:
                cancel_event.set()
                raise SchedulerError("worker returned an invalid worker_id.")
            if worker_id != expected_worker_id:
                cancel_event.set()
                raise SchedulerError(
                    f"worker {expected_worker_id} reported worker_id {worker_id}."
                )
            worker_busy[worker_id] = False

            if selected_log_policy is WorkerLogPolicy.FORWARD and logfn is not None:
                for worker_message in message.get("logs") or ():
                    logfn(str(worker_message))

            message_type = message.get("type")
            if message_type == "error":
                cancel_event.set()
                if selected_partial_policy is PartialResultPolicy.YIELD_COMPLETED:
                    for index, result in message.get("results") or ():
                        yield accept_result(worker_id, int(index), result)
                raise WorkerExecutionError(
                    worker_id,
                    str(message.get("error") or "Unknown worker error."),
                    str(message.get("traceback") or ""),
                )
            if message_type != "chunk_done":
                cancel_event.set()
                raise SchedulerError(
                    f"worker returned unknown message type: {message_type!r}."
                )

            bucket = message.get("bucket")
            if bucket is not None:
                worker_last_bucket[worker_id] = bucket
            if bool(message.get("canceled")):
                cancellation_requested = True
                cancel_event.set()
            for index, result in message.get("results") or ():
                yield accept_result(worker_id, int(index), result)

            if not cancellation_requested and len(completed) < total:
                assign_next(worker_id)

        if cancellation_requested:
            raise SchedulerCancelled("Canceled by user at a case boundary.")
    finally:
        cleanup_errors = _cleanup_workers(
            cancel_event,
            task_senders,
            result_receivers,
            child_connections,
            started_processes,
        )
        if cleanup_errors:
            detail = "Worker cleanup failed: " + "; ".join(cleanup_errors)
            active_error = sys.exception()
            if active_error is None or isinstance(active_error, GeneratorExit):
                raise SchedulerError(detail)
            active_error.add_note(detail)


def _execute_request_worker(
    request: CaseExecutionRequest,
    logfn: Callable[[str], None],
) -> CaseExecutionResult:
    return execute_case(request, warning_callback=logfn)


def iter_execution_results_parallel(
    requests: Sequence[CaseExecutionRequest],
    workers: int,
    *,
    log_policy: WorkerLogPolicy | str,
    partial_result_policy: PartialResultPolicy | str,
    execution_order: Sequence[int] | None = None,
    chunk_cases: int | None = None,
    cancel_cb: Callable[[], bool] | None = None,
    logfn: Callable[[str], None] | None = None,
    progress_cb: Callable[[SchedulerProgress], None] | None = None,
    snapshot_cb: Callable[
        [tuple[tuple[int, CaseExecutionResult], ...]],
        None,
    ]
    | None = None,
) -> Iterator[tuple[int, CaseExecutionResult]]:
    """Run Phase 5 requests through the same one-case engine in spawn workers."""
    normalized = tuple(requests)
    yield from iter_case_results_parallel(
        normalized,
        workers,
        _execute_request_worker,
        log_policy=log_policy,
        partial_result_policy=partial_result_policy,
        execution_order=execution_order,
        bucket_keys=case_execution_bucket_keys(normalized),
        affinity_hints=case_execution_affinity_hints(normalized),
        chunk_cases=chunk_cases,
        cancel_cb=cancel_cb,
        logfn=logfn,
        progress_cb=progress_cb,
        snapshot_cb=snapshot_cb,
    )


__all__ = (
    "PartialResultPolicy",
    "SchedulerCancelled",
    "SchedulerError",
    "SchedulerProgress",
    "WorkerExecutionError",
    "WorkerLogPolicy",
    "WorkerStartupError",
    "WorkerUnexpectedExitError",
    "case_execution_bucket_keys",
    "iter_case_results_parallel",
    "iter_execution_results_parallel",
    "ordered_success_snapshot",
    "resolve_parallel_chunk_cases",
    "reuse_oriented_execution_order",
)
