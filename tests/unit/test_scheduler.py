from __future__ import annotations

import multiprocessing as mp
import os
import signal
import tempfile
import threading
import time
import unittest
from collections import OrderedDict, deque
from itertools import product
from pathlib import Path
from unittest import mock

import pytest

import panelsolver.core.scheduler as scheduler_module
from panelsolver.core import (
    PartialResultPolicy,
    SchedulerCancelled,
    SchedulerError,
    SchedulingAffinityHint,
    WorkerExecutionError,
    WorkerLogPolicy,
    WorkerStartupError,
    WorkerUnexpectedExitError,
    iter_case_results_parallel,
    ordered_success_snapshot,
    resolve_parallel_chunk_cases,
)

_ORIGINAL_WORKER_PROCESS_ENTRY = scheduler_module._worker_process_entry


def _delayed_worker_process_entry(*args) -> None:
    time.sleep(0.5)
    _ORIGINAL_WORKER_PROCESS_ENTRY(*args)


def _exit_before_ready_process_entry(worker_id, *args) -> None:
    if worker_id == 0:
        os._exit(7)
    time.sleep(0.5)
    _ORIGINAL_WORKER_PROCESS_ENTRY(worker_id, *args)


def _success_worker(case: tuple[int, float], logfn) -> int:
    value, delay_seconds = case
    time.sleep(delay_seconds)
    logfn(f"case={value}")
    return value * 10


def _failure_worker(case: int, logfn) -> int:
    logfn(f"case={case}")
    if case == 1:
        raise ValueError("deliberate worker failure")
    return case * 10


def _unexpected_exit_worker(case: int, _logfn) -> int:
    if case == 0:
        os._exit(7)
    time.sleep(0.3)
    return case


def _unpickleable_worker(case: str, logfn):
    if case == "result":
        return lambda: None
    if case == "log":
        logfn(lambda: None)
        return 1
    if case == "error":
        raise ValueError("failure after an unpickleable partial result")
    return 1


def _identity_worker(case, _logfn):
    return case


def _pid_worker(case: tuple[str, float], _logfn) -> tuple[int, str]:
    label, delay_seconds = case
    time.sleep(delay_seconds)
    return os.getpid(), label


def _synchronized_affinity_worker(
    case: tuple[str, str, str, str],
    _logfn,
) -> tuple[int, str]:
    label, behavior, release_text, accepted_text = case
    release = Path(release_text)
    accepted = Path(accepted_text)
    deadline = time.monotonic() + 5.0

    if behavior == "wait_for_release":
        while not release.exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("affinity probe release was not signaled")
            time.sleep(0.005)
    elif behavior == "release_then_wait_for_accept":
        release.touch()
        while not accepted.exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("affinity probe result was not accepted")
            time.sleep(0.005)
    elif behavior != "immediate":
        raise RuntimeError(f"unknown affinity probe behavior: {behavior}")
    return os.getpid(), label


def _touch_after_delay(path_text: str) -> None:
    time.sleep(0.02)
    Path(path_text).touch()


def _large_result_worker(case: tuple[str, str, str], _logfn):
    behavior, ready_text, release_text = case
    ready = Path(ready_text)
    release = Path(release_text)
    if behavior == "large":
        payload = b"x" * (64 * 1024 * 1024)
        ready.touch()
        deadline = time.monotonic() + 5.0
        while not release.exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("large-result release was not signaled")
            time.sleep(0.005)
        return payload
    deadline = time.monotonic() + 5.0
    while not ready.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("large-result worker did not become ready")
        time.sleep(0.005)
    threading.Thread(
        target=_touch_after_delay,
        args=(release_text,),
        daemon=True,
    ).start()
    return 1


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


def _worker_resource_state() -> tuple[set[int], set[int]]:
    process_ids = {
        int(process.pid) for process in mp.active_children() if process.pid is not None
    }
    feeder_ids = {
        int(thread.ident)
        for thread in threading.enumerate()
        if thread.name == "QueueFeederThread" and thread.ident is not None
    }
    return process_ids, feeder_ids


class SchedulerTests(unittest.TestCase):
    def assert_no_new_worker_resources(
        self,
        before: tuple[set[int], set[int]],
    ) -> None:
        deadline = time.monotonic() + 2.0
        while True:
            after = _worker_resource_state()
            new_processes = after[0] - before[0]
            new_feeders = after[1] - before[1]
            if not new_processes and not new_feeders:
                return
            if time.monotonic() >= deadline:
                self.fail(
                    f"worker resources leaked: processes={sorted(new_processes)}, "
                    f"queue_feeders={sorted(new_feeders)}"
                )
            time.sleep(0.02)

    def test_chunk_value_and_default_validation(self) -> None:
        self.assertEqual(2, resolve_parallel_chunk_cases(2))
        self.assertEqual(8, resolve_parallel_chunk_cases())
        for value in (0, True, "bad"):
            with self.subTest(value=value), self.assertRaises(SchedulerError):
                resolve_parallel_chunk_cases(value)

    def test_bucket_chunking_stably_groups_higher_priority_affinities(self) -> None:
        high_a = SchedulingAffinityHint(("high", "a"), priority=2)
        high_b = SchedulingAffinityHint(("high", "b"), priority=2)
        low = SchedulingAffinityHint(("low", "c"), priority=1)
        hints = (
            (low,),
            (high_a,),
            (high_b,),
            (high_a, low),
            (high_b,),
            (low,),
            (),
            (),
        )

        chunks, remaining = scheduler_module._build_bucket_chunks(
            tuple(range(len(hints))),
            ("ray",) * len(hints),
            hints,
            2,
        )

        self.assertEqual(
            ((1, 3), (2, 4), (0, 5), (6, 7)),
            tuple(chunks["ray"]),
        )
        self.assertEqual({"ray": len(hints)}, remaining)

    def test_bucket_chunking_closes_before_splitting_the_next_group(self) -> None:
        affinity_a = SchedulingAffinityHint(("cache", "a"), priority=1)
        affinity_b = SchedulingAffinityHint(("cache", "b"), priority=1)
        hints = ((affinity_a,),) * 3 + ((affinity_b,),) * 3

        chunks, _remaining = scheduler_module._build_bucket_chunks(
            tuple(range(len(hints))),
            ("ray",) * len(hints),
            hints,
            4,
        )

        self.assertEqual(((0, 1, 2), (3, 4, 5)), tuple(chunks["ray"]))

    def test_bucket_chunking_splits_deterministically_to_keep_baseline_count(
        self,
    ) -> None:
        affinities = tuple(
            SchedulingAffinityHint(("cache", identity), priority=1)
            for identity in ("a", "b", "c")
        )
        hints = tuple((affinity,) for affinity in affinities for _ in range(5))
        decisions = []

        for _ in range(5):
            chunks, _remaining = scheduler_module._build_bucket_chunks(
                tuple(range(len(hints))),
                ("ray",) * len(hints),
                hints,
                8,
            )
            decisions.append(tuple(chunks["ray"]))

        self.assertEqual([decisions[0]] * 5, decisions)
        self.assertEqual(2, len(decisions[0]))
        self.assertTrue(all(len(chunk) <= 8 for chunk in decisions[0]))
        self.assertEqual(tuple(range(15)), sum(decisions[0], ()))
        for group in (range(5), range(5, 10), range(10, 15)):
            self.assertEqual(
                tuple(group),
                tuple(
                    index for chunk in decisions[0] for index in chunk if index in group
                ),
            )

    def test_affinity_chunk_count_matches_fixed_width_baseline(self) -> None:
        for chunk_cases in range(1, 7):
            for group_sizes in product(range(1, 7), repeat=3):
                next_index = 0
                groups = []
                for size in group_sizes:
                    groups.append(tuple(range(next_index, next_index + size)))
                    next_index += size

                chunks = scheduler_module._chunks_preserving_affinity_groups(
                    groups,
                    chunk_cases,
                )
                baseline_count = (next_index + chunk_cases - 1) // chunk_cases
                with self.subTest(
                    chunk_cases=chunk_cases,
                    group_sizes=group_sizes,
                ):
                    self.assertEqual(baseline_count, len(chunks))
                    self.assertTrue(
                        all(1 <= len(chunk) <= chunk_cases for chunk in chunks)
                    )
                    self.assertEqual(tuple(range(next_index)), sum(chunks, ()))

    def test_none_and_empty_affinities_preserve_fifo_bucket_chunking(self) -> None:
        order = (5, 2, 0, 4, 1, 3)
        bucket_keys = ("a", "a", "b", "a", "b", "a")
        raw_hints = (None, tuple(() for _ in bucket_keys))

        for provided in raw_hints:
            with self.subTest(provided="none" if provided is None else "empty"):
                hints = scheduler_module._validated_affinity_hints(
                    len(bucket_keys),
                    provided,
                )
                chunks, remaining = scheduler_module._build_bucket_chunks(
                    order,
                    bucket_keys,
                    hints,
                    2,
                )
                self.assertEqual(("a", "b"), tuple(chunks))
                self.assertEqual(((5, 0), (1, 3)), tuple(chunks["a"]))
                self.assertEqual(((2, 4),), tuple(chunks["b"]))
                self.assertEqual({"a": 4, "b": 2}, remaining)

    def test_primary_bucket_continuity_precedes_secondary_affinity(self) -> None:
        cone = SchedulingAffinityHint(("cone", 5.0, 1.4), priority=2)
        bucket_chunks = {
            "ray-a": deque(((1,), (2,))),
            "ray-b": deque(((3,), (4,), (5,))),
        }
        picked = scheduler_module._pick_next_chunk(
            0,
            ["ray-a"],
            [OrderedDict(((cone.identity, None),))],
            bucket_chunks,
            {"ray-a": 2, "ray-b": 3},
            {"ray-a": 0, "ray-b": None},
            {"ray-a": 0, "ray-b": 1},
            ((), (), (cone,), (cone,), (cone,), (cone,)),
        )
        # Primary locality wins across buckets and consumes the next chunk that
        # was prebuilt for that bucket.
        self.assertEqual(("ray-a", (1,)), picked)

    def test_unowned_bucket_precedes_affine_owned_bucket(self) -> None:
        cone = SchedulingAffinityHint(("cone", 5.0, 1.4), priority=2)
        picked = scheduler_module._pick_next_chunk(
            1,
            [None, None],
            [OrderedDict(), OrderedDict(((cone.identity, None),))],
            {
                "owned": deque(((0,), (1,), (2,), (3,))),
                "unowned": deque(((4,),)),
            },
            {"owned": 4, "unowned": 1},
            {"owned": 0, "unowned": None},
            {"owned": 0, "unowned": 1},
            ((cone,), (cone,), (cone,), (cone,), ()),
        )
        self.assertEqual(("unowned", (4,)), picked)

    def test_unowned_bucket_prefers_cone_then_wedge_affinity(self) -> None:
        cone = SchedulingAffinityHint(("cone", 5.0, 1.4), priority=2)
        wedge = SchedulingAffinityHint(("wedge", 5.0, 1.4), priority=1)
        picked = scheduler_module._pick_next_chunk(
            0,
            [None],
            [OrderedDict(((cone.identity, None), (wedge.identity, None)))],
            {
                "wedge-ray": deque(((0,),)),
                "cone-ray": deque(((1,),)),
            },
            {"wedge-ray": 1, "cone-ray": 1},
            {"wedge-ray": None, "cone-ray": None},
            {"wedge-ray": 0, "cone-ray": 1},
            ((wedge,), (cone,)),
        )
        self.assertEqual(("cone-ray", (1,)), picked)

    def test_unowned_bucket_reuses_wedge_affinity(self) -> None:
        wedge = SchedulingAffinityHint(("wedge", 10.0, 1.4), priority=1)
        picked = scheduler_module._pick_next_chunk(
            0,
            [None],
            [OrderedDict(((wedge.identity, None),))],
            {"miss": deque(((0,),)), "hit": deque(((1,),))},
            {"miss": 1, "hit": 1},
            {"miss": None, "hit": None},
            {"miss": 0, "hit": 1},
            ((), (wedge,)),
        )
        self.assertEqual(("hit", (1,)), picked)

    def test_empty_affinity_preserves_largest_unowned_bucket_policy(self) -> None:
        picked = scheduler_module._pick_next_chunk(
            0,
            [None],
            [OrderedDict()],
            {"small": deque(((0,),)), "large": deque(((1,), (2,)))},
            {"small": 1, "large": 2},
            {"small": None, "large": None},
            {"small": 0, "large": 1},
            ((), (), ()),
        )
        self.assertEqual(("large", (1,)), picked)

    def test_owned_bucket_steal_values_remaining_work_before_affinity(self) -> None:
        cone = SchedulingAffinityHint(("cone", 5.0, 1.4), priority=2)
        picked = scheduler_module._pick_next_chunk(
            2,
            [None, None, None],
            [OrderedDict(), OrderedDict(), OrderedDict(((cone.identity, None),))],
            {
                "large-miss": deque(((0,), (1,), (2,))),
                "small-hit": deque(((3,),)),
            },
            {"large-miss": 3, "small-hit": 1},
            {"large-miss": 0, "small-hit": 1},
            {"large-miss": 0, "small-hit": 1},
            ((), (), (), (cone,)),
        )
        self.assertEqual(("large-miss", (0,)), picked)

    def test_owned_bucket_steal_uses_affinity_after_remaining_work(self) -> None:
        cone = SchedulingAffinityHint(("cone", 5.0, 1.4), priority=2)
        picked = scheduler_module._pick_next_chunk(
            2,
            [None, None, None],
            [OrderedDict(), OrderedDict(), OrderedDict(((cone.identity, None),))],
            {"miss": deque(((0,),)), "hit": deque(((1,),))},
            {"miss": 1, "hit": 1},
            {"miss": 0, "hit": 1},
            {"miss": 0, "hit": 1},
            ((), (cone,)),
        )
        self.assertEqual(("hit", (1,)), picked)

    def test_affinity_ties_are_deterministic(self) -> None:
        decisions = []
        for _ in range(5):
            decisions.append(
                scheduler_module._pick_next_chunk(
                    0,
                    [None],
                    [OrderedDict()],
                    {"first": deque(((0,),)), "second": deque(((1,),))},
                    {"first": 1, "second": 1},
                    {"first": None, "second": None},
                    {"first": 0, "second": 1},
                    ((), ()),
                )
            )
        self.assertEqual([("first", (0,))] * 5, decisions)

    def test_worker_affinity_history_is_bounded_lru(self) -> None:
        history: OrderedDict[object, None] = OrderedDict()
        for index in range(scheduler_module._MAX_WORKER_AFFINITIES + 3):
            scheduler_module._record_worker_affinities(
                history,
                (SchedulingAffinityHint(("cache", index)),),
            )
        self.assertEqual(scheduler_module._MAX_WORKER_AFFINITIES, len(history))
        self.assertNotIn(("cache", 0), history)
        self.assertIn(
            ("cache", scheduler_module._MAX_WORKER_AFFINITIES + 2),
            history,
        )

    @pytest.mark.slow
    def test_completion_progress_logs_and_ordered_snapshots(self) -> None:
        before = _worker_resource_state()
        logs: list[str] = []
        progress = []
        snapshots = []
        cases = ((0, 0.15), (1, 0.0), (2, 0.02))
        results = list(
            iter_case_results_parallel(
                cases,
                2,
                _success_worker,
                log_policy=WorkerLogPolicy.FORWARD,
                partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                execution_order=(2, 0, 1),
                chunk_cases=1,
                logfn=logs.append,
                progress_cb=progress.append,
                snapshot_cb=snapshots.append,
            )
        )
        self.assertEqual({(0, 0), (1, 10), (2, 20)}, set(results))
        self.assertEqual([1, 2, 3], [event.completed for event in progress])
        self.assertEqual(3, progress[-1].total)
        self.assertEqual({"case=0", "case=1", "case=2"}, set(logs))
        self.assertEqual(((2, 20), (0, 0), (1, 10)), snapshots[-1])
        self.assertEqual(
            ((2, 20), (0, 0), (1, 10)),
            ordered_success_snapshot(dict(results), (2, 0, 1)),
        )
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_successful_results_guide_later_worker_affinity_without_ray_steal(
        self,
    ) -> None:
        before = _worker_resource_state()
        affinity_a = SchedulingAffinityHint(("cone", 5.0, 1.4), priority=2)
        affinity_b = SchedulingAffinityHint(("cone", 10.0, 1.4), priority=2)

        def run_probe(affinity_hints=None, snapshot_cb=None):
            with tempfile.TemporaryDirectory() as temporary:
                release = Path(temporary) / "release"
                accepted = Path(temporary) / "accepted"
                # Keep the initial B worker busy until A receives its next case,
                # then keep that A worker busy until the parent accepts B-first.
                # This fixes both dispatch decisions without timing assumptions.
                cases = (
                    ("a-first", "immediate", str(release), str(accepted)),
                    ("b-first", "wait_for_release", str(release), str(accepted)),
                    (
                        "b-next",
                        "release_then_wait_for_accept",
                        str(release),
                        str(accepted),
                    ),
                    (
                        "a-next",
                        "release_then_wait_for_accept",
                        str(release),
                        str(accepted),
                    ),
                )

                def record_progress(event):
                    if event.case_index == 1:
                        accepted.touch()

                return dict(
                    iter_case_results_parallel(
                        cases,
                        2,
                        _synchronized_affinity_worker,
                        log_policy=WorkerLogPolicy.DROP,
                        partial_result_policy=PartialResultPolicy.YIELD_COMPLETED,
                        bucket_keys=("ray-a1", "ray-b1", "ray-b2", "ray-a2"),
                        affinity_hints=affinity_hints,
                        chunk_cases=1,
                        progress_cb=record_progress,
                        snapshot_cb=snapshot_cb,
                    )
                )

        snapshots = []
        baseline = run_probe()
        results = run_probe(
            (
                (affinity_a,),
                (affinity_b,),
                (affinity_b,),
                (affinity_a,),
            ),
            snapshots.append,
        )
        baseline_hits = int(baseline[0][0] == baseline[3][0]) + int(
            baseline[1][0] == baseline[2][0]
        )
        affinity_hits = int(results[0][0] == results[3][0]) + int(
            results[1][0] == results[2][0]
        )
        self.assertEqual(0, baseline_hits)
        self.assertEqual(2, affinity_hits)
        self.assertEqual((0, 1, 2, 3), tuple(index for index, _ in snapshots[-1]))
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_bucket_local_grouping_reduces_worker_affinity_spread_without_more_steal(
        self,
    ) -> None:
        before = _worker_resource_state()
        affinity_a = SchedulingAffinityHint(("expensive", "a"), priority=2)
        affinity_b = SchedulingAffinityHint(("expensive", "b"), priority=2)
        cases = (
            ("a", 0.03),
            ("b", 0.03),
            ("a", 0.03),
            ("b", 0.03),
            ("a", 0.03),
            ("b", 0.03),
        )
        order = (1, 0, 3, 2, 5, 4)

        def run_probe(affinity_hints=None, snapshot_cb=None):
            return dict(
                iter_case_results_parallel(
                    cases,
                    2,
                    _pid_worker,
                    log_policy=WorkerLogPolicy.DROP,
                    partial_result_policy=PartialResultPolicy.YIELD_COMPLETED,
                    execution_order=order,
                    bucket_keys=("one-ray-bucket",) * len(cases),
                    affinity_hints=affinity_hints,
                    chunk_cases=4,
                    snapshot_cb=snapshot_cb,
                )
            )

        baseline = run_probe()
        snapshots = []
        grouped = run_probe(
            (
                (affinity_a,),
                (affinity_b,),
                (affinity_a,),
                (affinity_b,),
                (affinity_a,),
                (affinity_b,),
            ),
            snapshots.append,
        )

        def affinity_worker_spread(results, label):
            return len({result[0] for result in results.values() if result[1] == label})

        self.assertEqual(2, affinity_worker_spread(baseline, "a"))
        self.assertEqual(2, affinity_worker_spread(baseline, "b"))
        self.assertEqual(1, affinity_worker_spread(grouped, "a"))
        self.assertEqual(1, affinity_worker_spread(grouped, "b"))
        # Both modes use one owner plus one steal for the sole primary bucket.
        self.assertEqual(2, len({result[0] for result in baseline.values()}))
        self.assertEqual(2, len({result[0] for result in grouped.values()}))
        self.assertEqual(order, tuple(index for index, _ in snapshots[-1]))
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_bucket_local_grouping_does_not_add_ray_workers_when_groups_conflict(
        self,
    ) -> None:
        before = _worker_resource_state()
        labels = ("a", "b", "c")
        affinities = {
            label: SchedulingAffinityHint(("cache", label), priority=1)
            for label in labels
        }
        cases = tuple((label, 0.02) for _ in range(5) for label in labels)
        hints = tuple((affinities[label],) for label, _delay in cases)
        order = tuple(reversed(range(len(cases))))

        def run_probe(affinity_hints=None, snapshot_cb=None):
            return dict(
                iter_case_results_parallel(
                    cases,
                    3,
                    _pid_worker,
                    log_policy=WorkerLogPolicy.DROP,
                    partial_result_policy=PartialResultPolicy.YIELD_COMPLETED,
                    execution_order=order,
                    bucket_keys=("one-ray-bucket",) * len(cases),
                    affinity_hints=affinity_hints,
                    chunk_cases=8,
                    snapshot_cb=snapshot_cb,
                )
            )

        baseline = run_probe()
        snapshots = []
        grouped = run_probe(hints, snapshots.append)
        baseline_pids = {result[0] for result in baseline.values()}
        grouped_pids = {result[0] for result in grouped.values()}

        self.assertEqual(2, len(baseline_pids))
        self.assertEqual(2, len(grouped_pids))
        self.assertLessEqual(len(grouped_pids), len(baseline_pids))
        self.assertEqual(order, tuple(index for index, _ in snapshots[-1]))
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_forward_logs_and_discard_failed_chunk_results(self) -> None:
        before = _worker_resource_state()
        logs: list[str] = []
        yielded: list[tuple[int, int]] = []
        iterator = iter_case_results_parallel(
            (0, 1, 2),
            2,
            _failure_worker,
            log_policy=WorkerLogPolicy.FORWARD,
            partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
            bucket_keys=("same", "same", "same"),
            chunk_cases=3,
            logfn=logs.append,
        )
        with self.assertRaises(WorkerExecutionError) as caught:
            yielded.extend(iterator)
        self.assertEqual([], yielded)
        self.assertEqual(["case=0", "case=1"], logs)
        self.assertIn("deliberate worker failure", caught.exception.remote_error)
        self.assertIn("ValueError", caught.exception.remote_traceback)
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_drop_logs_and_yield_completed_failed_chunk_results(self) -> None:
        before = _worker_resource_state()
        logs: list[str] = []
        iterator = iter_case_results_parallel(
            (0, 1, 2),
            2,
            _failure_worker,
            log_policy=WorkerLogPolicy.DROP,
            partial_result_policy=PartialResultPolicy.YIELD_COMPLETED,
            bucket_keys=("same", "same", "same"),
            chunk_cases=3,
            logfn=logs.append,
        )
        self.assertEqual((0, 0), next(iterator))
        with self.assertRaises(WorkerExecutionError):
            next(iterator)
        self.assertEqual([], logs)
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_drop_logs_and_discard_failed_chunk_results_remain_orthogonal(
        self,
    ) -> None:
        before = _worker_resource_state()
        logs: list[str] = []
        yielded: list[tuple[int, int]] = []
        iterator = iter_case_results_parallel(
            (0, 1, 2),
            2,
            _failure_worker,
            log_policy=WorkerLogPolicy.DROP,
            partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
            bucket_keys=("same", "same", "same"),
            chunk_cases=3,
            logfn=logs.append,
        )
        with self.assertRaises(WorkerExecutionError):
            yielded.extend(iterator)
        self.assertEqual([], yielded)
        self.assertEqual([], logs)
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_forward_logs_and_yield_completed_failed_chunk_results_remain_orthogonal(
        self,
    ) -> None:
        before = _worker_resource_state()
        logs: list[str] = []
        iterator = iter_case_results_parallel(
            (0, 1, 2),
            2,
            _failure_worker,
            log_policy=WorkerLogPolicy.FORWARD,
            partial_result_policy=PartialResultPolicy.YIELD_COMPLETED,
            bucket_keys=("same", "same", "same"),
            chunk_cases=3,
            logfn=logs.append,
        )
        self.assertEqual((0, 0), next(iterator))
        with self.assertRaises(WorkerExecutionError):
            next(iterator)
        self.assertEqual(["case=0", "case=1"], logs)
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_cancellation_waits_for_case_boundary_and_stops_dispatch(self) -> None:
        before = _worker_resource_state()
        progress = []
        yielded: list[tuple[int, int]] = []

        def cancel_after_first_completion() -> bool:
            return bool(progress)

        iterator = iter_case_results_parallel(
            ((0, 0.02), (1, 0.15), (2, 0.15), (3, 0.15)),
            2,
            _success_worker,
            log_policy=WorkerLogPolicy.DROP,
            partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
            chunk_cases=1,
            cancel_cb=cancel_after_first_completion,
            progress_cb=progress.append,
        )
        with self.assertRaises(SchedulerCancelled):
            yielded.extend(iterator)
        self.assertGreaterEqual(len(yielded), 1)
        self.assertLess(len(yielded), 4)
        self.assertEqual(
            list(range(1, len(yielded) + 1)), [p.completed for p in progress]
        )
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_unexpected_exit_is_reported_with_exit_code(self) -> None:
        before = _worker_resource_state()
        with self.assertRaises(WorkerUnexpectedExitError) as caught:
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
        self.assertIn((0, 7), caught.exception.exits)
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_fast_unexpected_exit_is_repeatable_after_all_workers_are_ready(
        self,
    ) -> None:
        before = _worker_resource_state()
        for _ in range(5):
            with self.assertRaises(WorkerUnexpectedExitError):
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
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_unpickleable_result_is_a_bounded_worker_error(self) -> None:
        before = _worker_resource_state()
        with self.assertRaisesRegex(
            WorkerExecutionError, "serialize worker chunk_done"
        ):
            list(
                iter_case_results_parallel(
                    ("result", "ok"),
                    2,
                    _unpickleable_worker,
                    log_policy=WorkerLogPolicy.DROP,
                    partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                    bucket_keys=("same", "same"),
                    chunk_cases=2,
                )
            )
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_unpickleable_case_is_rejected_before_pipe_dispatch(self) -> None:
        before = _worker_resource_state()
        unpickleable_case = lambda: None
        with self.assertRaisesRegex(SchedulerError, "serialize worker task"):
            list(
                iter_case_results_parallel(
                    (unpickleable_case, 1),
                    2,
                    _identity_worker,
                    log_policy=WorkerLogPolicy.DROP,
                    partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                    chunk_cases=1,
                )
            )
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_unpickleable_partial_result_is_a_bounded_delivery_error(
        self,
    ) -> None:
        before = _worker_resource_state()
        yielded = []
        iterator = iter_case_results_parallel(
            ("result", "error"),
            2,
            _unpickleable_worker,
            log_policy=WorkerLogPolicy.DROP,
            partial_result_policy=PartialResultPolicy.YIELD_COMPLETED,
            bucket_keys=("same", "same"),
            chunk_cases=2,
        )
        with self.assertRaisesRegex(
            WorkerExecutionError,
            "serialize worker error",
        ) as caught:
            yielded.extend(iterator)
        self.assertEqual([], yielded)
        self.assertIn(
            "failure after an unpickleable partial result",
            str(caught.exception),
        )
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_early_close_interrupts_a_backpressured_large_result(self) -> None:
        before = _worker_resource_state()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            ready = str(root / "large-ready")
            release = str(root / "large-release")
            iterator = iter_case_results_parallel(
                (("large", ready, release), ("fast", ready, release)),
                2,
                _large_result_worker,
                log_policy=WorkerLogPolicy.DROP,
                partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                bucket_keys=("large", "fast"),
                chunk_cases=1,
            )
            self.assertEqual((1, 1), next(iterator))
            time.sleep(0.05)
            started = time.monotonic()
            iterator.close()
            self.assertLess(time.monotonic() - started, 7.0)
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_unpickleable_forwarded_log_is_a_bounded_worker_error(self) -> None:
        before = _worker_resource_state()
        with self.assertRaisesRegex(
            WorkerExecutionError, "serialize worker chunk_done"
        ):
            list(
                iter_case_results_parallel(
                    ("log", "ok"),
                    2,
                    _unpickleable_worker,
                    log_policy=WorkerLogPolicy.FORWARD,
                    partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                    bucket_keys=("same", "same"),
                    chunk_cases=2,
                )
            )
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_early_iterator_close_kills_and_reaps_a_resistant_worker(self) -> None:
        before = _worker_resource_state()
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
            self.assertEqual((1, 1), next(iterator))
            started = time.monotonic()
            iterator.close()
            self.assertLess(time.monotonic() - started, 7.0)
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_cleanup_failure_during_generator_close_is_not_hidden(self) -> None:
        before = _worker_resource_state()
        original_cleanup = scheduler_module._cleanup_workers

        def cleanup_with_report(*args):
            errors = original_cleanup(*args)
            return (*errors, "synthetic cleanup failure")

        with mock.patch.object(
            scheduler_module,
            "_cleanup_workers",
            side_effect=cleanup_with_report,
        ):
            iterator = iter_case_results_parallel(
                ((0, 0.0), (1, 0.1)),
                2,
                _success_worker,
                log_policy=WorkerLogPolicy.DROP,
                partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                chunk_cases=1,
            )
            next(iterator)
            with self.assertRaisesRegex(SchedulerError, "synthetic cleanup failure"):
                iterator.close()
        self.assert_no_new_worker_resources(before)

    def test_cleanup_reports_a_process_that_survives_kill_without_blocking(
        self,
    ) -> None:
        calls: list[str] = []

        class FakeEvent:
            def set(self) -> None:
                calls.append("cancel")

        class FakeConnection:
            def __init__(self, name: str) -> None:
                self.name = name

            def send_bytes(self, _payload: bytes) -> None:
                calls.append(f"{self.name}:send")

            def close(self) -> None:
                calls.append(f"{self.name}:close")

        class FakeProcess:
            pid = 4242

            def is_alive(self) -> bool:
                return True

            def join(self, timeout=None) -> None:
                calls.append(f"join:{timeout is not None}")

            def terminate(self) -> None:
                calls.append("terminate")

            def kill(self) -> None:
                calls.append("kill")

            def close(self) -> None:
                calls.append("process:close")

        errors = scheduler_module._cleanup_workers(
            FakeEvent(),
            (FakeConnection("task"),),
            (FakeConnection("result"),),
            (FakeConnection("child"),),
            (FakeProcess(),),
        )
        self.assertTrue(any("remained alive after kill" in error for error in errors))
        self.assertIn("terminate", calls)
        self.assertIn("kill", calls)
        self.assertNotIn("task:send", calls)
        self.assertNotIn("process:close", calls)
        self.assertTrue(
            all(call == "join:True" for call in calls if call.startswith("join"))
        )

    @pytest.mark.slow
    def test_mid_frame_connection_failure_is_a_worker_exit_error(self) -> None:
        before = _worker_resource_state()
        connection_base = scheduler_module.mp.connection._ConnectionBase
        original_recv_bytes = connection_base.recv_bytes
        failed = False

        def fail_after_readiness(connection, *args, **kwargs):
            nonlocal failed
            payload = original_recv_bytes(connection, *args, **kwargs)
            message = scheduler_module._decode_worker_message(payload)
            if message.get("type") != "ready" and not failed:
                failed = True
                raise OSError("got end of file during message")
            return payload

        with mock.patch.object(
            connection_base,
            "recv_bytes",
            new=fail_after_readiness,
        ):
            with self.assertRaises(WorkerUnexpectedExitError):
                list(
                    iter_case_results_parallel(
                        ((0, 0.0), (1, 0.05)),
                        2,
                        _success_worker,
                        log_policy=WorkerLogPolicy.DROP,
                        partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                        chunk_cases=1,
                    )
                )
        self.assertTrue(failed)
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_readiness_cancellation_is_typed_bounded_and_reaps_workers(self) -> None:
        before = _worker_resource_state()
        calls = 0

        def cancel_during_readiness() -> bool:
            nonlocal calls
            calls += 1
            return calls >= 2

        with mock.patch.object(
            scheduler_module,
            "_worker_process_entry",
            new=_delayed_worker_process_entry,
        ):
            with self.assertRaises(SchedulerCancelled) as caught:
                list(
                    iter_case_results_parallel(
                        (0, 1),
                        2,
                        _identity_worker,
                        log_policy=WorkerLogPolicy.DROP,
                        partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                        cancel_cb=cancel_during_readiness,
                    )
                )
        self.assertEqual("Canceled by user at a case boundary.", str(caught.exception))
        self.assertGreaterEqual(calls, 2)
        self.assert_no_new_worker_resources(before)

    @pytest.mark.slow
    def test_real_pre_ready_exit_is_an_unexpected_exit_without_chain(self) -> None:
        before = _worker_resource_state()
        with mock.patch.object(
            scheduler_module,
            "_worker_process_entry",
            new=_exit_before_ready_process_entry,
        ):
            with self.assertRaises(WorkerUnexpectedExitError) as caught:
                list(
                    iter_case_results_parallel(
                        (0, 1),
                        2,
                        _identity_worker,
                        log_policy=WorkerLogPolicy.DROP,
                        partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                    )
                )
        self.assertEqual(((0, 7),), caught.exception.exits)
        self.assertIsNone(caught.exception.__cause__)
        self.assertIsNone(caught.exception.__context__)
        self.assert_no_new_worker_resources(before)

    def test_readiness_poll_and_eof_known_exit_share_unexpected_type(self) -> None:
        class DeadProcess:
            exitcode = 7

            def is_alive(self) -> bool:
                return False

            def join(self, timeout=None) -> None:
                self.join_timeout = timeout

        class EofConnection:
            def recv_bytes(self) -> bytes:
                raise EOFError("synthetic pre-ready EOF")

        for mode in ("poll", "eof"):
            with self.subTest(mode=mode):
                process = DeadProcess()
                connection = EofConnection()
                readable = [] if mode == "poll" else [connection]
                with mock.patch.object(
                    scheduler_module,
                    "wait_connections",
                    return_value=readable,
                ):
                    with self.assertRaises(WorkerUnexpectedExitError) as caught:
                        scheduler_module._wait_for_worker_readiness(
                            (connection,),
                            (process,),
                        )
                self.assertEqual(((0, 7),), caught.exception.exits)
                self.assertIsNone(caught.exception.__cause__)
                self.assertIsNone(caught.exception.__context__)
                self.assertEqual(
                    scheduler_module._CLEANUP_SECONDS, process.join_timeout
                )

    def test_readiness_eof_with_live_process_retains_startup_transport_chain(
        self,
    ) -> None:
        class LiveProcess:
            exitcode = None

            def is_alive(self) -> bool:
                return True

            def join(self, timeout=None) -> None:
                self.join_timeout = timeout

        class EofConnection:
            def recv_bytes(self) -> bytes:
                raise EOFError("synthetic live pre-ready EOF")

        process = LiveProcess()
        connection = EofConnection()
        with mock.patch.object(
            scheduler_module,
            "wait_connections",
            return_value=[connection],
        ):
            with self.assertRaises(WorkerStartupError) as caught:
                scheduler_module._wait_for_worker_readiness(
                    (connection,),
                    (process,),
                )
        self.assertIs(type(caught.exception.__cause__), EOFError)
        self.assertIs(caught.exception.__cause__, caught.exception.__context__)
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertEqual(scheduler_module._CLEANUP_SECONDS, process.join_timeout)

    def test_unpickleable_spawn_callable_is_rejected_before_child_start(self) -> None:
        before = _worker_resource_state()
        local_worker = lambda case, _logfn: case
        with self.assertRaisesRegex(
            WorkerStartupError,
            "serialize spawn worker callable",
        ):
            list(
                iter_case_results_parallel(
                    (0, 1),
                    2,
                    local_worker,
                    log_policy=WorkerLogPolicy.DROP,
                    partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                )
            )
        self.assert_no_new_worker_resources(before)

    def test_os_spawn_start_failure_is_wrapped_without_child_leak(self) -> None:
        before = _worker_resource_state()
        process_type = scheduler_module.mp.get_context("spawn").Process
        original_start = process_type.start
        calls = 0

        def fail_first_start(process):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("synthetic spawn failure")
            return original_start(process)

        with mock.patch.object(process_type, "start", new=fail_first_start):
            with self.assertRaisesRegex(WorkerStartupError, "synthetic spawn failure"):
                list(
                    iter_case_results_parallel(
                        (0, 1),
                        2,
                        _identity_worker,
                        log_policy=WorkerLogPolicy.DROP,
                        partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                    )
                )
        self.assertEqual(1, calls)
        self.assert_no_new_worker_resources(before)

    def test_requires_explicit_policies_and_valid_complete_order(self) -> None:
        with self.assertRaisesRegex(SchedulerError, "log_policy"):
            list(
                iter_case_results_parallel(
                    (0, 1),
                    2,
                    _failure_worker,
                    log_policy="merge",
                    partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                )
            )
        with self.assertRaisesRegex(SchedulerError, "exactly once"):
            list(
                iter_case_results_parallel(
                    (0, 1),
                    2,
                    _failure_worker,
                    log_policy=WorkerLogPolicy.DROP,
                    partial_result_policy=PartialResultPolicy.DISCARD_CHUNK,
                    execution_order=(0, 0),
                )
            )


if __name__ == "__main__":
    unittest.main()
