"""Policy-driven domain execution and artifact orchestration."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from trimesh import ray as trimesh_ray

from panelsolver.core import (
    ArtifactProjectionPolicy,
    CaseExecutionResult,
    CsvCell,
    CsvProjection,
    CsvProjectionPolicy,
    PartialResultPolicy,
    SchedulerCancelled,
    SchedulerError,
    WorkerLogPolicy,
    case_execution_bucket_keys,
    execute_case,
    iter_case_results_parallel,
    project_summary_csv,
    project_vtp_artifact,
    reuse_oriented_execution_order,
)
from panelsolver.core.execution import case_execution_affinity_hints
from panelsolver.models import ModelRegistry

from .artifact_io import write_vtp_projection
from .case_adapter import AdaptedCase, ProductCasePolicy, adapt_case_row
from .csv_writer import AtomicCsvWritePolicy, write_csv_atomic
from .environment import resolve_parallel_chunk_environment
from .output_status import OutputIssue, OutputKind, OutputPhase
from .versioning import panelsolver_distribution_version

type CaseRow = Mapping[str, object]
type LogCallback = Callable[[str], None]
type ProgressCallback = Callable[[int, int], None]
type CancelCallback = Callable[[], bool]
type SnapshotCallback = Callable[[CsvProjection, int, int, bool], None]
type ProjectionAdditionsBuilder = Callable[
    [CaseRow, CaseExecutionResult], "ProductProjectionAdditions"
]

_RAY_ACCEL_HINTED_PRODUCTS: set[str] = set()
DEFAULT_CHECKPOINT_CASES = 2000


@dataclass(frozen=True, slots=True)
class ProductProjectionAdditions:
    """Product-owned result fields around the shared projection envelope."""

    csv_values: Mapping[str, CsvCell] = field(default_factory=dict)
    vtp_field_data: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("csv_values", "vtp_field_data"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise TypeError(f"ProductProjectionAdditions.{name} must be a mapping")
            object.__setattr__(self, name, dict(value))


@dataclass(frozen=True, slots=True)
class ProductRuntimePolicy:
    """Independent domain decisions required by common orchestration."""

    product_id: str
    case_policy: ProductCasePolicy
    csv_projection_policy: CsvProjectionPolicy
    csv_write_policy: AtomicCsvWritePolicy
    worker_log_policy: WorkerLogPolicy
    partial_result_policy: PartialResultPolicy
    build_projection_additions: ProjectionAdditionsBuilder

    def __post_init__(self) -> None:
        if not isinstance(self.case_policy, ProductCasePolicy):
            raise TypeError("case_policy must be a ProductCasePolicy")
        if self.product_id != self.case_policy.product_id:
            raise ValueError("runtime and case policy product IDs must match")
        if not isinstance(self.csv_projection_policy, CsvProjectionPolicy):
            raise TypeError("csv_projection_policy must be a CsvProjectionPolicy")
        if not isinstance(self.csv_write_policy, AtomicCsvWritePolicy):
            raise TypeError("csv_write_policy must be an AtomicCsvWritePolicy")
        if not isinstance(self.worker_log_policy, WorkerLogPolicy):
            raise TypeError("worker_log_policy must be a WorkerLogPolicy")
        if not isinstance(self.partial_result_policy, PartialResultPolicy):
            raise TypeError("partial_result_policy must be a PartialResultPolicy")
        if not callable(self.build_projection_additions):
            raise TypeError("build_projection_additions must be callable")


@dataclass(frozen=True, slots=True)
class PreparedProductCase:
    """One input row and its model-neutral request prepared in the parent."""

    row: Mapping[str, object]
    adapted: AdaptedCase
    policy: ProductRuntimePolicy

    def __post_init__(self) -> None:
        if not isinstance(self.row, Mapping):
            raise TypeError("row must be a mapping")
        if not isinstance(self.adapted, AdaptedCase):
            raise TypeError("adapted must be an AdaptedCase")
        if not isinstance(self.policy, ProductRuntimePolicy):
            raise TypeError("policy must be a ProductRuntimePolicy")
        object.__setattr__(self, "row", dict(self.row))


@dataclass(frozen=True, slots=True)
class ProductCaseRunResult:
    """One computed case plus its exact projection and output status."""

    csv: CsvProjection
    vtp_path: str
    output_issues: tuple[OutputIssue, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.csv, CsvProjection):
            raise TypeError("csv must be a CsvProjection")
        issues = tuple(self.output_issues)
        if any(not isinstance(issue, OutputIssue) for issue in issues):
            raise TypeError("output_issues must contain OutputIssue values")
        object.__setattr__(self, "vtp_path", str(self.vtp_path))
        object.__setattr__(self, "output_issues", issues)


@dataclass(frozen=True, slots=True)
class ProductBatchRunResult:
    """Input-ordered computed cases, projection, and independent output status."""

    cases: tuple[ProductCaseRunResult, ...]
    csv: CsvProjection
    output_issues: tuple[OutputIssue, ...] = ()
    summary_csv_saved: bool | None = None

    def __post_init__(self) -> None:
        cases = tuple(self.cases)
        if not cases or any(
            not isinstance(case, ProductCaseRunResult) for case in cases
        ):
            raise TypeError("cases must contain ProductCaseRunResult values")
        if not isinstance(self.csv, CsvProjection):
            raise TypeError("csv must be a CsvProjection")
        issues = tuple(self.output_issues)
        if any(not isinstance(issue, OutputIssue) for issue in issues):
            raise TypeError("output_issues must contain OutputIssue values")
        if self.summary_csv_saved is not None and not isinstance(
            self.summary_csv_saved, bool
        ):
            raise TypeError("summary_csv_saved must be a boolean or None")
        object.__setattr__(self, "cases", cases)
        object.__setattr__(self, "output_issues", issues)


def prepare_product_cases(
    rows: Sequence[CaseRow],
    policy: ProductRuntimePolicy,
    *,
    registry: ModelRegistry | None = None,
) -> tuple[PreparedProductCase, ...]:
    """Adapt input rows once while retaining product policy as data."""
    if not isinstance(policy, ProductRuntimePolicy):
        raise TypeError("policy must be a ProductRuntimePolicy")
    records = tuple(rows)
    if not records:
        raise ValueError("rows must not be empty")
    if any(not isinstance(row, Mapping) for row in records):
        raise TypeError("rows must contain mappings")
    if any("save_npz_on" in row for row in records):
        raise ValueError(
            "save_npz_on has been removed. Delete this field; "
            "Panel Solver no longer writes NPZ files."
        )
    if registry is None:
        from .execution import default_model_registry

        selected_registry = default_model_registry()
    else:
        selected_registry = registry
    if not isinstance(selected_registry, ModelRegistry):
        raise TypeError("registry must be a ModelRegistry")
    return tuple(
        PreparedProductCase(
            row,
            adapt_case_row(row, policy.case_policy, registry=selected_registry),
            policy,
        )
        for row in records
    )


def combine_csv_projections(
    projections: Sequence[CsvProjection],
) -> CsvProjection:
    """Combine already-input-ordered case projections without re-sorting rows."""
    values = tuple(projections)
    if not values:
        raise ValueError("projections must not be empty")
    if any(not isinstance(value, CsvProjection) for value in values):
        raise TypeError("projections must contain CsvProjection values")
    columns = values[0].columns
    if any(value.columns != columns for value in values[1:]):
        raise ValueError("all case projections must have identical columns")
    return CsvProjection(columns, tuple(row for value in values for row in value.rows))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _csv_input_row(row: CaseRow) -> dict[str, CsvCell]:
    normalized: dict[str, CsvCell] = {}
    for name, raw_value in row.items():
        value = raw_value.item() if isinstance(raw_value, np.generic) else raw_value
        if isinstance(value, float) and math.isnan(value):
            value = None
        elif isinstance(value, Path):
            value = str(value)
        if value is not None and not isinstance(value, (str, bool, int, float)):
            value = str(value)
        normalized[str(name)] = value
    return normalized


def _run_prepared_product_case(
    prepared: PreparedProductCase,
    logfn: LogCallback,
) -> ProductCaseRunResult:
    """Compute one case and retain output failures without failing the worker."""
    started_at = _utc_now()
    started_clock = time.perf_counter()
    row = prepared.row
    case_id = str(row["case_id"])
    out_dir = Path(str(row.get("out_dir", "outputs"))).expanduser()
    vtp_file = out_dir / f"{case_id}.vtp"
    save_vtp = bool(int(row.get("save_vtp_on", 1)))

    execution = execute_case(
        prepared.adapted.request,
        warning_callback=logfn,
    )
    additions = prepared.policy.build_projection_additions(row, execution)
    if not isinstance(additions, ProductProjectionAdditions):
        raise TypeError(
            "build_projection_additions must return ProductProjectionAdditions"
        )
    solver_version = panelsolver_distribution_version()
    output_issues: list[OutputIssue] = []
    directory_ready = True
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        directory_ready = False
        issue = OutputIssue(
            OutputKind.OUTPUT_DIRECTORY,
            OutputPhase.PREPARE,
            str(out_dir),
            str(exc) or type(exc).__name__,
            case_id,
        )
        output_issues.append(issue)
        logfn(
            "[ERROR] Output directory preparation failed: "
            f"case_id={case_id} path={out_dir} reason={issue.message}"
        )

    saved_vtp_path = ""
    if save_vtp and directory_ready:
        try:
            artifact_policy = ArtifactProjectionPolicy(
                attitude_input_used=prepared.adapted.attitude.input_mode,
                case_signature=execution.signature.digest,
                ray_backend_used=execution.shielding.config.effective_backend,
                solver_version=solver_version,
                vtp_field_data=additions.vtp_field_data,
            )
            write_vtp_projection(
                vtp_file,
                project_vtp_artifact(
                    execution.mesh,
                    execution.results,
                    artifact_policy,
                ),
            )
            saved_vtp_path = str(vtp_file)
        except Exception as exc:
            issue = OutputIssue(
                OutputKind.VTP,
                OutputPhase.WRITE,
                str(vtp_file),
                str(exc) or type(exc).__name__,
                case_id,
            )
            output_issues.append(issue)
            logfn(
                "[ERROR] VTP output failed: "
                f"case_id={case_id} path={vtp_file} reason={issue.message}"
            )
    finished_at = _utc_now()
    run_values: dict[str, CsvCell] = {
        "solver_version": solver_version,
        "case_signature": execution.signature.digest,
        "run_started_at_utc": started_at,
        "run_finished_at_utc": finished_at,
        "run_elapsed_s": float(time.perf_counter() - started_clock),
        "out_attitude_input": prepared.adapted.attitude.input_mode,
        "ray_backend_used": execution.shielding.config.effective_backend,
        "vtp_path": saved_vtp_path,
        **additions.csv_values,
    }
    component_sources = {
        component.component_id: component.source
        for component in execution.mesh.components
    }
    csv_projection = project_summary_csv(
        _csv_input_row(row),
        execution.results,
        prepared.policy.csv_projection_policy,
        run_values=run_values,
        component_sources=component_sources,
    )
    return ProductCaseRunResult(
        csv_projection,
        saved_vtp_path,
        tuple(output_issues),
    )


def _execution_order(
    prepared: Sequence[PreparedProductCase],
) -> tuple[int, ...]:
    """Use core's exact shielding-first reuse order without output reordering."""
    return reuse_oriented_execution_order(
        tuple(case.adapted.request for case in prepared)
    )


def _maybe_log_ray_accel_hint(policy: ProductRuntimePolicy, logfn: LogCallback) -> None:
    if policy.product_id in _RAY_ACCEL_HINTED_PRODUCTS:
        return
    if trimesh_ray.has_embree:
        logfn("[INFO] Ray backend: Embree (ray_pyembree).")
    else:
        logfn(
            "[INFO] Ray backend: rtree (ray_triangle). Optional acceleration is "
            "available: checkout users can run uv sync --extra rayaccel; "
            "release users should reinstall the current GitHub Release wheel "
            "with the rayaccel extra (see Installation)."
        )
    _RAY_ACCEL_HINTED_PRODUCTS.add(policy.product_id)


def run_product_cases(
    rows: Sequence[CaseRow],
    policy: ProductRuntimePolicy,
    *,
    workers: int = 1,
    logfn: LogCallback | None = None,
    progress_cb: ProgressCallback | None = None,
    cancel_cb: CancelCallback | None = None,
    checkpoint_every_cases: int | None = DEFAULT_CHECKPOINT_CASES,
    snapshot_cb: SnapshotCallback | None = None,
    registry: ModelRegistry | None = None,
) -> ProductBatchRunResult:
    """Run cases with product-selected scheduler and checkpoint behavior."""
    logger = (lambda _message: None) if logfn is None else logfn
    if not callable(logger):
        raise TypeError("logfn must be callable")
    if progress_cb is not None and not callable(progress_cb):
        raise TypeError("progress_cb must be callable")
    if cancel_cb is not None and not callable(cancel_cb):
        raise TypeError("cancel_cb must be callable")
    if snapshot_cb is not None and not callable(snapshot_cb):
        raise TypeError("snapshot_cb must be callable")
    if isinstance(workers, bool) or not isinstance(workers, int):
        raise TypeError("workers must be an integer")
    checkpoint_every = int(checkpoint_every_cases or 0)
    if checkpoint_every < 0:
        raise ValueError("checkpoint_every_cases must be >= 0.")
    if cancel_cb is not None and cancel_cb():
        raise SchedulerCancelled("Canceled by user at a case boundary.")

    cases = prepare_product_cases(rows, policy, registry=registry)
    total = len(cases)
    order = _execution_order(cases)
    completed: list[ProductCaseRunResult | None] = [None] * total
    completed_since_snapshot = 0
    done = 0
    _maybe_log_ray_accel_hint(policy, logger)

    def snapshot(force: bool) -> None:
        nonlocal completed_since_snapshot
        if snapshot_cb is None:
            return
        if not force and (
            checkpoint_every <= 0 or completed_since_snapshot < checkpoint_every
        ):
            return
        available = tuple(case for case in completed if case is not None)
        if not available:
            return
        snapshot_cb(
            combine_csv_projections(tuple(case.csv for case in available)),
            done,
            total,
            force,
        )
        completed_since_snapshot = 0

    def accept(index: int, result: ProductCaseRunResult, *, parallel: bool) -> None:
        nonlocal completed_since_snapshot, done
        completed[index] = result
        done += 1
        completed_since_snapshot += 1
        snapshot(False)
        if parallel:
            logger(f"[OK] ({done}/{total}) case_id={cases[index].row['case_id']}")
        if progress_cb is not None:
            progress_cb(done, total)

    if workers <= 1 or total <= 1:
        for run_index, index in enumerate(order, start=1):
            if cancel_cb is not None and cancel_cb():
                raise SchedulerCancelled("Canceled by user at a case boundary.")
            logger(f"[RUN] ({run_index}/{total}) case_id={cases[index].row['case_id']}")
            accept(
                index, _run_prepared_product_case(cases[index], logger), parallel=False
            )
    else:
        logger(f"[RUN] Parallel execution with {workers} worker(s)")
        requests = tuple(case.adapted.request for case in cases)
        parallel_results = iter_case_results_parallel(
            cases,
            workers,
            _run_prepared_product_case,
            log_policy=policy.worker_log_policy,
            partial_result_policy=policy.partial_result_policy,
            execution_order=order,
            bucket_keys=case_execution_bucket_keys(requests),
            affinity_hints=case_execution_affinity_hints(requests),
            chunk_cases=resolve_parallel_chunk_environment(
                legacy_env_prefix=policy.case_policy.legacy_env_prefix,
            ),
            cancel_cb=cancel_cb,
            logfn=logger,
        )
        for index, result in parallel_results:
            try:
                accept(int(index), result, parallel=True)
            except BaseException as exc:
                try:
                    parallel_results.close()
                except SchedulerError as cleanup_exc:
                    exc.add_note(str(cleanup_exc))
                raise

    ordered = tuple(case for case in completed if case is not None)
    if len(ordered) != total:
        raise RuntimeError("case execution completed without every result")
    snapshot(True)
    projection = combine_csv_projections(tuple(case.csv for case in ordered))
    output_issues = tuple(issue for case in ordered for issue in case.output_issues)
    return ProductBatchRunResult(ordered, projection, output_issues)


def run_and_write_product_cases(
    rows: Sequence[CaseRow],
    policy: ProductRuntimePolicy,
    output_path: str | Path,
    *,
    workers: int = 1,
    logfn: LogCallback | None = None,
    progress_cb: ProgressCallback | None = None,
    cancel_cb: CancelCallback | None = None,
    checkpoint_every_cases: int = DEFAULT_CHECKPOINT_CASES,
    log_snapshots: bool = False,
) -> ProductBatchRunResult:
    """Run cases and atomically rewrite checkpoint/final summary snapshots."""
    logger = (lambda _message: None) if logfn is None else logfn
    output = Path(output_path)
    summary_issues: list[OutputIssue] = []
    complete_summary_saved = False
    last_successful_snapshot_done = 0

    def write_snapshot(
        projection: CsvProjection,
        done: int,
        total: int,
        is_final: bool,
    ) -> None:
        nonlocal complete_summary_saved, last_successful_snapshot_done
        if is_final and done == total == last_successful_snapshot_done:
            complete_summary_saved = True
            if log_snapshots:
                logger(
                    f"[SAVE] final {done}/{total} -> {output} "
                    "(complete checkpoint reused)"
                )
            return
        phase = OutputPhase.FINAL if is_final else OutputPhase.CHECKPOINT
        try:
            write_csv_atomic(output, projection, policy.csv_write_policy)
        except Exception as exc:
            issue = OutputIssue(
                OutputKind.SUMMARY_CSV,
                phase,
                str(output),
                str(exc) or type(exc).__name__,
            )
            summary_issues.append(issue)
            label = "final" if is_final else "checkpoint"
            logger(
                f"[ERROR] Summary CSV {label} output failed: "
                f"path={output} reason={issue.message}"
            )
            return
        last_successful_snapshot_done = done
        if done == total:
            complete_summary_saved = True
        if log_snapshots:
            label = "final" if is_final else "checkpoint"
            logger(f"[SAVE] {label} {done}/{total} -> {output}")

    result = run_product_cases(
        rows,
        policy,
        workers=workers,
        logfn=logger,
        progress_cb=progress_cb,
        cancel_cb=cancel_cb,
        checkpoint_every_cases=checkpoint_every_cases,
        snapshot_cb=write_snapshot,
    )
    issues = (*result.output_issues, *summary_issues)
    if issues:
        logger(f"[WARN] Run completed with {len(issues)} output error(s).")
    return ProductBatchRunResult(
        result.cases,
        result.csv,
        issues,
        complete_summary_saved,
    )


__all__ = (
    "DEFAULT_CHECKPOINT_CASES",
    "PreparedProductCase",
    "ProductBatchRunResult",
    "ProductCaseRunResult",
    "ProductProjectionAdditions",
    "ProductRuntimePolicy",
    "combine_csv_projections",
    "prepare_product_cases",
    "run_and_write_product_cases",
    "run_product_cases",
)
