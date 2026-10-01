"""Headless sectional batches over the existing physical case scheduler.

Workers project completed definitions immediately. Only compact CSV values and
failure labels cross the worker boundary or survive the batch; meshes and loads
are released after each case. Output writing is separate and repeatable.
"""

from __future__ import annotations

from collections.abc import Callable, Generator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from panelsolver.core import (
    CsvCell,
    CsvProjection,
    SchedulerCancelled,
    SchedulerError,
    case_execution_bucket_keys,
    execute_case,
    iter_case_results_parallel,
    reuse_oriented_execution_order,
)
from panelsolver.core._sectional_integration import (
    SectionalLoadResult,
    integrate_sectional_loads,
)
from panelsolver.core.execution import case_execution_affinity_hints
from panelsolver.core.sectional import resolve_sectional_load_spec

from .csv_writer import validate_csv_output_path, write_csv_atomic
from .environment import resolve_parallel_chunk_environment
from .path_resolution import absolute_input_path
from .runtime import (
    PreparedProductCase,
    ProductRuntimePolicy,
    prepare_product_cases,
)
from .sectional_definitions import SectionalDefinition

type BatchStatus = Literal["completed", "failed", "cancelled"]
type CaseRow = Mapping[str, object]
type LogCallback = Callable[[str], None]
type CancelCallback = Callable[[], bool]
type ProgressCallback = Callable[[int, int], None]

_STATUS_COLUMNS = ("batch_status", "requested_pairs", "completed_pairs")
SECTIONAL_CSV_COLUMNS = (
    "case_id",
    "case_signature",
    "section_id",
    *_STATUS_COLUMNS,
    *(f"origin_{axis}_stl_m" for axis in "xyz"),
    *(f"direction_{axis}_stl" for axis in "xyz"),
    *(f"direction_hat_{axis}_stl" for axis in "xyz"),
    "requested_component_ids",
    "selected_component_ids",
    "all_components_selected",
    "range_mode",
    "requested_start_m",
    "requested_stop_m",
    "resolved_start_m",
    "resolved_stop_m",
    "selected_geometry_min_m",
    "selected_geometry_max_m",
    "covers_selected_geometry",
    "bin_count",
    "Aref_m2",
    *(f"ref_{axis}_stl_m" for axis in "xyz"),
    "Lref_Cl_m",
    "Lref_Cm_m",
    "Lref_Cn_m",
    "alpha_stability_deg",
    "scope",
    "component_id",
    "bin_index",
    "bin_start_m",
    "bin_stop_m",
    "bin_center_m",
    "bin_width_m",
    "wetted_area_m2",
    *(
        f"delta_force_coeff_{axis}_{frame}"
        for frame in ("stl", "body", "stability")
        for axis in "xyz"
    ),
    *(f"delta_moment_area_coeff_{axis}_body_m" for axis in "xyz"),
    *(f"delta_moment_coeff_{axis}_body" for axis in "xyz"),
    *(f"delta_{name}" for name in ("CA", "CY", "CN", "CD", "CL", "Cl", "Cm", "Cn")),
)
_PAIR_COLUMNS = tuple(
    name for name in SECTIONAL_CSV_COLUMNS if name not in _STATUS_COLUMNS
)


@dataclass(frozen=True, slots=True)
class SectionalFailure:
    """An unsuccessful calculation, never represented by a zero result row."""

    case_id: str | None
    section_id: str | None
    message: str


@dataclass(frozen=True, slots=True)
class SectionalBatchResult:
    """Retained successes and terminal calculation status, independent of saving.

    Progress callbacks count completely processed cases. Pair counts count only
    successfully integrated definitions, including successful prefixes of a
    failed or cancelled case. A cancelled batch can contain all requested pairs
    when cancellation was observed at the final boundary.
    """

    csv: CsvProjection | None
    status: BatchStatus
    completed_pairs: int
    requested_pairs: int
    completed_cases: int
    total_cases: int
    errors: tuple[SectionalFailure, ...] = ()


@dataclass(frozen=True, slots=True)
class _PreparedSectionalCase:
    physical: PreparedProductCase
    definitions: tuple[SectionalDefinition, ...]


@dataclass(frozen=True, slots=True)
class _SectionalCaseResult:
    projections: tuple[CsvProjection, ...]
    errors: tuple[SectionalFailure, ...] = ()
    cancelled: bool = False


def _project_pair(
    result: SectionalLoadResult,
    section_id: str,
    signature: str,
) -> CsvProjection:
    spec, case = result.spec, result.case
    definition = spec.definition
    common: dict[str, CsvCell] = {
        "case_id": case.case_id,
        "case_signature": signature,
        "section_id": section_id,
        "requested_component_ids": (
            None
            if definition.component_ids is None
            else ";".join(map(str, definition.component_ids))
        ),
        "selected_component_ids": ";".join(map(str, spec.selected_component_ids)),
        "all_components_selected": spec.all_components_selected,
        "range_mode": spec.range_mode,
        "requested_start_m": definition.start_m,
        "requested_stop_m": definition.stop_m,
        "resolved_start_m": spec.resolved_start_m,
        "resolved_stop_m": spec.resolved_stop_m,
        "selected_geometry_min_m": spec.selected_geometry_min_m,
        "selected_geometry_max_m": spec.selected_geometry_max_m,
        "covers_selected_geometry": spec.covers_selected_geometry,
        "bin_count": definition.bin_count,
        "Aref_m2": case.Aref_m2,
        "Lref_Cl_m": case.Lref_Cl_m,
        "Lref_Cm_m": case.Lref_Cm_m,
        "Lref_Cn_m": case.Lref_Cn_m,
        "alpha_stability_deg": case.alpha_stability_deg,
    }
    for index, axis in enumerate("xyz"):
        common[f"origin_{axis}_stl_m"] = float(definition.axis_origin_stl_m[index])
        common[f"direction_{axis}_stl"] = float(definition.axis_direction_stl[index])
        common[f"direction_hat_{axis}_stl"] = float(
            definition.axis_direction_hat_stl[index]
        )
        common[f"ref_{axis}_stl_m"] = float(case.moment_reference_stl_m[index])
    scopes = (
        ("total", None, result.total),
        *(
            ("component", item.component_id, item.distribution)
            for item in result.components
        ),
    )
    rows: list[dict[str, CsvCell]] = []
    for scope, component_id, distribution in scopes:
        coefficients = {
            name: getattr(distribution, name)
            for name in ("CA", "CY", "CN", "CD", "CL", "Cl", "Cm", "Cn")
        }
        for bin_index in range(definition.bin_count):
            values: dict[str, CsvCell] = {
                **common,
                "scope": scope,
                "component_id": component_id,
                "bin_index": bin_index,
                "bin_start_m": float(spec.bin_edges_m[bin_index]),
                "bin_stop_m": float(spec.bin_edges_m[bin_index + 1]),
                "bin_center_m": float(spec.bin_centers_m[bin_index]),
                "bin_width_m": float(spec.bin_widths_m[bin_index]),
                "wetted_area_m2": float(distribution.wetted_area_m2[bin_index]),
                **{
                    f"delta_{name}": float(vector[bin_index])
                    for name, vector in coefficients.items()
                },
            }
            for frame in ("stl", "body", "stability"):
                vector = getattr(distribution, f"force_coeff_{frame}")[bin_index]
                for index, axis in enumerate("xyz"):
                    values[f"delta_force_coeff_{axis}_{frame}"] = float(vector[index])
            for index, axis in enumerate("xyz"):
                values[f"delta_moment_area_coeff_{axis}_body_m"] = float(
                    distribution.moment_area_coeff_body_m[bin_index, index]
                )
                values[f"delta_moment_coeff_{axis}_body"] = float(
                    distribution.moment_coeff_body[bin_index, index]
                )
            rows.append({name: values[name] for name in _PAIR_COLUMNS})
    return CsvProjection(_PAIR_COLUMNS, tuple(rows))


def _run_sectional_case(
    prepared: _PreparedSectionalCase,
    logfn: LogCallback,
    cancel_cb: CancelCallback | None = None,
) -> _SectionalCaseResult:
    """Execute physics once; a failed definition retains preceding successes."""
    case_id = prepared.physical.adapted.request.common_case.case_id
    projections: list[CsvProjection] = []
    section_id: str | None = None
    try:
        if cancel_cb is not None and cancel_cb():
            return _SectionalCaseResult((), cancelled=True)
        execution = execute_case(
            prepared.physical.adapted.request,
            warning_callback=logfn,
        )
        for item in prepared.definitions:
            if cancel_cb is not None and cancel_cb():
                return _SectionalCaseResult(tuple(projections), cancelled=True)
            section_id = item.section_id
            numerical = integrate_sectional_loads(
                execution.mesh,
                resolve_sectional_load_spec(execution.mesh, item.definition),
                execution.results.local_loads,
                execution.results.case,
            )
            projections.append(
                _project_pair(numerical, section_id, execution.signature.digest)
            )
            # No topology indices or load arrays remain in a completed projection.
            del numerical
    except Exception as exc:
        message = str(exc) or type(exc).__name__
        logfn(f"[ERROR] case_id={case_id!r} section_id={section_id!r}: {message}")
        return _SectionalCaseResult(
            tuple(projections), (SectionalFailure(case_id, section_id, message),)
        )
    return _SectionalCaseResult(tuple(projections))


def _parallel_sectional_case(
    prepared: _PreparedSectionalCase, logfn: LogCallback
) -> _SectionalCaseResult:
    # The common scheduler observes its process cancellation event between cases.
    return _run_sectional_case(prepared, logfn)


def _finish_batch(
    completed: Sequence[_SectionalCaseResult | None],
    definitions_count: int,
    status: BatchStatus,
    extra_errors: Sequence[SectionalFailure] = (),
) -> SectionalBatchResult:
    available = tuple(result for result in completed if result is not None)
    completed_pairs = sum(len(result.projections) for result in available)
    requested_pairs = len(completed) * definitions_count
    values: dict[str, CsvCell] = {
        "batch_status": status,
        "requested_pairs": requested_pairs,
        "completed_pairs": completed_pairs,
    }
    rows = tuple(
        {
            name: values[name] if name in values else row[name]
            for name in SECTIONAL_CSV_COLUMNS
        }
        for result in available
        for projection in result.projections
        for row in projection.rows
    )
    return SectionalBatchResult(
        csv=CsvProjection(SECTIONAL_CSV_COLUMNS, rows) if rows else None,
        status=status,
        completed_pairs=completed_pairs,
        requested_pairs=requested_pairs,
        completed_cases=sum(
            len(result.projections) == definitions_count for result in available
        ),
        total_cases=len(completed),
        errors=(
            *(error for result in available for error in result.errors),
            *extra_errors,
        ),
    )


def run_sectional_cases(
    rows: Sequence[CaseRow],
    policy: ProductRuntimePolicy,
    definitions: Sequence[SectionalDefinition],
    *,
    workers: int = 1,
    logfn: LogCallback | None = None,
    progress_cb: ProgressCallback | None = None,
    cancel_cb: CancelCallback | None = None,
) -> SectionalBatchResult:
    """Compute selected cases × definitions and retain input-ordered successes.

    Failures stop new dispatch cooperatively. Already-dispatched parallel cases
    may finish; their returned successes are retained. Serial cancellation is
    checked before each case/definition, parallel cancellation between cases.
    A failure-triggered scheduler cancellation retains the ``failed`` status.
    """
    records = tuple(dict(row) for row in rows)
    selected = tuple(definitions)
    if not records:
        raise ValueError("rows must not be empty")
    if not selected or any(
        not isinstance(item, SectionalDefinition) for item in selected
    ):
        raise ValueError("definitions must contain SectionalDefinition values")
    if len({item.section_id for item in selected}) != len(selected):
        raise ValueError("definitions must have unique section_id values")
    if isinstance(workers, bool) or not isinstance(workers, int) or workers < 1:
        raise ValueError("workers must be an integer >= 1")
    if not isinstance(policy, ProductRuntimePolicy):
        raise TypeError("policy must be a ProductRuntimePolicy")
    logger = (lambda _message: None) if logfn is None else logfn
    for name, callback in (
        ("logfn", logger),
        ("progress_cb", progress_cb),
        ("cancel_cb", cancel_cb),
    ):
        if callback is not None and not callable(callback):
            raise TypeError(f"{name} must be callable")
    completed: list[_SectionalCaseResult | None] = [None] * len(records)
    status: BatchStatus = "completed"
    stop_requested = False

    def stopping() -> bool:
        nonlocal stop_requested, status
        if cancel_cb is not None and cancel_cb():
            stop_requested = True
            if status != "failed":
                status = "cancelled"
        return stop_requested

    if stopping():
        return _finish_batch(completed, len(selected), status)
    # Prepare all rows before any solve, preserving exact domain adaptation,
    # including Sentman's Mode B. Per-row calls attach a useful failure identity.
    prepared: list[_PreparedSectionalCase] = []
    for row in records:
        try:
            physical = prepare_product_cases((row,), policy)[0]
        except Exception as exc:
            return _finish_batch(
                completed,
                len(selected),
                "failed",
                (SectionalFailure(str(row.get("case_id", "")), None, str(exc)),),
            )
        prepared.append(_PreparedSectionalCase(physical, selected))
    requests = tuple(item.physical.adapted.request for item in prepared)
    order = reuse_oriented_execution_order(requests)
    processed = 0

    def accept(index: int, result: _SectionalCaseResult) -> None:
        nonlocal status, stop_requested, processed
        completed[index] = result
        if result.errors:
            status = "failed"
            stop_requested = True
        elif result.cancelled:
            if status != "failed":
                status = "cancelled"
            stop_requested = True
        if len(result.projections) == len(selected):
            processed += 1
        if progress_cb is not None:
            progress_cb(processed, len(records))

    extra_errors: list[SectionalFailure] = []
    if workers == 1 or len(prepared) == 1:
        for index in order:
            if stopping():
                break
            logger(f"[RUN] case_id={requests[index].common_case.case_id!r}")
            accept(index, _run_sectional_case(prepared[index], logger, stopping))
        stopping()
    else:
        parallel = iter_case_results_parallel(
            prepared,
            workers,
            _parallel_sectional_case,
            log_policy=policy.worker_log_policy,
            partial_result_policy=policy.partial_result_policy,
            execution_order=order,
            bucket_keys=case_execution_bucket_keys(requests),
            affinity_hints=case_execution_affinity_hints(requests),
            chunk_cases=resolve_parallel_chunk_environment(),
            cancel_cb=stopping,
            logfn=logger,
        )
        try:
            for index, result in parallel:
                # Do not break/close here: the scheduler must drain active cases
                # before its normal cleanup, rather than terminate their physics.
                accept(index, result)
        except SchedulerCancelled as exc:
            if status != "failed":
                status = "cancelled"
            # Scheduler cleanup attaches errors to the primary cancellation.
            # A cancellation with leaked/failed cleanup is not a clean stop.
            for note in getattr(exc, "__notes__", ()):
                status = "failed"
                extra_errors.append(SectionalFailure(None, None, note))
        except SchedulerError as exc:
            status = "failed"
            message = "\n".join((str(exc), *getattr(exc, "__notes__", ())))
            extra_errors.append(SectionalFailure(None, None, message))
        except BaseException as exc:
            # Only an exceptional consumer failure takes the scheduler's bounded
            # emergency cleanup path. Normal cancellation drains above.
            try:
                cast(Generator[tuple[int, _SectionalCaseResult]], parallel).close()
            except SchedulerError as cleanup_exc:
                exc.add_note(str(cleanup_exc))
            raise
        stopping()
    return _finish_batch(completed, len(selected), status, extra_errors)


def sectional_protected_paths(
    input_path: str | Path,
    definition_path: str | Path,
    rows: Sequence[CaseRow],
) -> tuple[Path, ...]:
    """Snapshot all loaded input paths, before filtering cases for a run.

    Keep both absolute source paths and resolved targets so later symlink changes
    cannot remove the original input target from export protection.
    """
    source = absolute_input_path(input_path)
    protected: list[Path] = []

    def add(path: Path) -> None:
        for candidate in (path, path.resolve(strict=False)):
            if candidate not in protected:
                protected.append(candidate)

    add(source)
    add(absolute_input_path(definition_path))
    for row in rows:
        for token in str(row.get("stl_path", "")).split(";"):
            if token.strip():
                path = Path(token.strip()).expanduser()
                add(path if path.is_absolute() else source.parent / path)
    return tuple(protected)


def write_sectional_csv(
    output_path: str | Path,
    result: SectionalBatchResult,
    protected_paths: Sequence[str | Path],
) -> Path:
    """Revalidate and atomically export retained successes without recomputing."""
    if not isinstance(result, SectionalBatchResult):
        raise TypeError("result must be a SectionalBatchResult")
    if result.csv is None:
        raise ValueError("No completed sectional results to export; output unchanged")
    output = validate_csv_output_path(output_path, protected_paths)
    write_csv_atomic(output, result.csv)
    return output


__all__ = (
    "SECTIONAL_CSV_COLUMNS",
    "SectionalBatchResult",
    "SectionalFailure",
    "run_sectional_cases",
    "sectional_protected_paths",
    "write_sectional_csv",
)
