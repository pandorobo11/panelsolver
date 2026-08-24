"""Canonical FMF application composition around the Sentman model."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from panelsolver.app import (
    COMMON_SCALAR_LABELS,
    DEFAULT_CHECKPOINT_CASES,
    ArtifactSignatureCandidates,
    GuiRunRequest,
    GuiRunResult,
    ProductBatchRunResult,
    ProductProjectionAdditions,
    ProductRuntimePolicy,
    SolverGuiAdapters,
    SolverSpec,
    run_and_write_product_cases,
    run_product_cases,
)
from panelsolver.app.case_adapter import AdaptedCase, ProductCasePolicy, adapt_case_row
from panelsolver.app.case_io import (
    AddIssue,
    CaseReaderPolicy,
    InputValidationError,
    ValidationIssue,
    is_filled,
    read_case_table,
)
from panelsolver.app.cli import ProductCliPolicy
from panelsolver.app.csv_writer import (
    DURABLE_CSV_WRITE_POLICY,
    validate_summary_output_path,
    write_csv_atomic,
)
from panelsolver.app.examples import ExampleDefinition
from panelsolver.core import (
    CaseExecutionResult,
    CommonResults,
    CsvCell,
    CsvProjection,
    CsvProjectionPolicy,
    MeshValidationPolicy,
    PartialResultPolicy,
    WorkerLogPolicy,
    prepare_case_signature,
    project_summary_csv,
)
from panelsolver.models import ModelRegistry
from panelsolver.models.sentman_atmosphere import altitude_range_km

REQUIRED = (
    "case_id",
    "stl_path",
    "stl_scale_m_per_unit",
    "alpha_deg",
    "beta_or_bank_deg",
    "Tw_K",
    "ref_x_m",
    "ref_y_m",
    "ref_z_m",
    "Aref_m2",
    "Lref_Cl_m",
    "Lref_Cm_m",
    "Lref_Cn_m",
)
INPUT_COLUMN_ORDER = (
    "case_id",
    "stl_path",
    "stl_scale_m_per_unit",
    "S",
    "Ti_K",
    "Mach",
    "Altitude_km",
    "Tw_K",
    "alpha_deg",
    "beta_or_bank_deg",
    "attitude_input",
    "ref_x_m",
    "ref_y_m",
    "ref_z_m",
    "Aref_m2",
    "Lref_Cl_m",
    "Lref_Cm_m",
    "Lref_Cn_m",
    "shielding_on",
    "ray_backend",
    "out_dir",
    "save_vtp_on",
)
NUMERIC_REQUIRED = (
    "stl_scale_m_per_unit",
    "alpha_deg",
    "beta_or_bank_deg",
    "Tw_K",
    "ref_x_m",
    "ref_y_m",
    "ref_z_m",
    "Aref_m2",
    "Lref_Cl_m",
    "Lref_Cm_m",
    "Lref_Cn_m",
)
NUMERIC_OPTIONAL = ("S", "Ti_K", "Mach", "Altitude_km")
POSITIVE_COLUMNS = frozenset(
    {
        "stl_scale_m_per_unit",
        "Tw_K",
        "Aref_m2",
        "Lref_Cl_m",
        "Lref_Cm_m",
        "Lref_Cn_m",
    }
)
DEFAULTS = {
    "shielding_on": 0,
    "save_vtp_on": 1,
    "ray_backend": "auto",
    "attitude_input": "beta_tan",
    "out_dir": "outputs",
}


def _validate_rows(frame: pd.DataFrame, add_issue: AddIssue) -> None:
    mode_a_s = frame["S"].notna()
    mode_a_ti = frame["Ti_K"].notna()
    mode_b_mach = frame["Mach"].notna()
    mode_b_altitude = frame["Altitude_km"].notna()
    for index in frame.index[mode_a_s ^ mode_a_ti]:
        add_issue(int(index), "S,Ti_K", "Mode A requires both 'S' and 'Ti_K'.")
    for index in frame.index[mode_b_mach ^ mode_b_altitude]:
        add_issue(
            int(index),
            "Mach,Altitude_km",
            "Mode B requires both 'Mach' and 'Altitude_km'.",
        )
    mode_a = mode_a_s & mode_a_ti
    mode_b = mode_b_mach & mode_b_altitude
    for index in frame.index[mode_a & mode_b]:
        add_issue(int(index), "mode", "Specify either Mode A or Mode B, not both.")
    for index in frame.index[(~mode_a) & (~mode_b)]:
        add_issue(
            int(index),
            "mode",
            "Specify one complete mode "
            "(Mode A: S+Ti_K, Mode B: Mach+Altitude_km).",
        )
    for column in ("S", "Ti_K", "Mach"):
        for index in frame.index[frame[column].notna() & (frame[column] <= 0.0)]:
            add_issue(int(index), column, "must be > 0 when specified.")
    minimum, maximum = altitude_range_km()
    finite = frame["Altitude_km"].notna() & np.isfinite(frame["Altitude_km"])
    invalid = finite & (
        (frame["Altitude_km"] < minimum) | (frame["Altitude_km"] > maximum)
    )
    for index in frame.index[invalid]:
        add_issue(
            int(index),
            "Altitude_km",
            f"must be within [{minimum}, {maximum}] km.",
        )


CASE_READER_POLICY = CaseReaderPolicy(
    required_columns=REQUIRED,
    input_columns=INPUT_COLUMN_ORDER,
    numeric_required=NUMERIC_REQUIRED,
    numeric_optional=NUMERIC_OPTIONAL,
    positive_columns=POSITIVE_COLUMNS,
    defaults=DEFAULTS,
    validate_rows=_validate_rows,
    required_numeric_message_style="split",
    keep_default_na=True,
    fill_defaults_by_presence=False,
)


def read_cases(path: str | Path) -> pd.DataFrame:
    """Read and validate the current FMF case-table contract."""
    return read_case_table(path, CASE_READER_POLICY)


def _optional_number(row: Mapping[str, object], name: str) -> float | None:
    value = row.get(name)
    return float(value) if is_filled(value) else None


def _model_payload(row: Mapping[str, object]) -> Mapping[str, object]:
    return {
        "S": _optional_number(row, "S"),
        "Ti_K": _optional_number(row, "Ti_K"),
        "Mach": _optional_number(row, "Mach"),
        "Altitude_km": _optional_number(row, "Altitude_km"),
        "Tw_K": float(row["Tw_K"]),
    }


CASE_POLICY = ProductCasePolicy(
    product_id="fmf",
    model_id="sentman",
    legacy_env_prefix="FMFSOLVER",
    mesh_validation_policy=MeshValidationPolicy.STRICT,
    model_payload=_model_payload,
)


def adapt_row(
    row: Mapping[str, object],
    *,
    registry: ModelRegistry | None = None,
) -> AdaptedCase:
    """Adapt one normalized FMF row to the shared execution request."""
    return adapt_case_row(row, CASE_POLICY, registry=registry)


def build_primary_signatures(
    row: Mapping[str, object],
    *,
    registry: ModelRegistry | None = None,
) -> ArtifactSignatureCandidates:
    """Build only the current panelsolver.case v1 artifact identity."""
    primary = prepare_case_signature(adapt_row(row, registry=registry).request)
    return ArtifactSignatureCandidates(primary)


CSV_PROJECTION_POLICY = CsvProjectionPolicy(
    input_columns=INPUT_COLUMN_ORDER,
    result_columns=(
        "solver_version",
        "case_signature",
        "run_started_at_utc",
        "run_finished_at_utc",
        "run_elapsed_s",
        "mode",
        "out_S",
        "out_Ti_K",
        "out_attitude_input",
        "alpha_t_deg_resolved",
        "beta_t_deg_resolved",
        "scope",
        "component_id",
        "component_stl_path",
        "ray_backend_used",
        "CA",
        "CY",
        "CN",
        "Cl",
        "Cm",
        "Cn",
        "CD",
        "CL",
        "faces",
        "shielded_faces",
        "vtp_path",
    ),
)
CSV_WRITE_POLICY = DURABLE_CSV_WRITE_POLICY


def project_csv(
    input_row: Mapping[str, CsvCell],
    results: CommonResults,
    *,
    run_values: Mapping[str, CsvCell],
    component_sources: Mapping[int, str] | None = None,
) -> CsvProjection:
    return project_summary_csv(
        input_row,
        results,
        CSV_PROJECTION_POLICY,
        run_values=run_values,
        component_sources=component_sources,
    )


def validate_results_output_path(
    out_path: str | Path,
    input_path: str | Path,
    case_rows: Iterable[Mapping[str, object]] = (),
) -> Path:
    return validate_summary_output_path(out_path, input_path, case_rows)


def write_csv(out_path: str | Path, projection: CsvProjection) -> None:
    write_csv_atomic(out_path, projection, CSV_WRITE_POLICY)


def _projection_additions(
    _row: Mapping[str, object],
    execution: CaseExecutionResult,
) -> ProductProjectionAdditions:
    metadata = execution.results.local_loads.metadata
    return ProductProjectionAdditions(
        csv_values={
            "mode": str(metadata["mode"]),
            "out_S": float(metadata["S"]),
            "out_Ti_K": float(metadata["Ti_K"]),
        },
    )


RUNTIME_POLICY = ProductRuntimePolicy(
    product_id="fmf",
    case_policy=CASE_POLICY,
    csv_projection_policy=CSV_PROJECTION_POLICY,
    csv_write_policy=CSV_WRITE_POLICY,
    worker_log_policy=WorkerLogPolicy.FORWARD,
    partial_result_policy=PartialResultPolicy.YIELD_COMPLETED,
    build_projection_additions=_projection_additions,
)


def run_cases(
    rows: Sequence[Mapping[str, object]],
    *,
    workers: int = 1,
    logfn=None,
    progress_cb=None,
    cancel_cb=None,
    checkpoint_every_cases: int | None = DEFAULT_CHECKPOINT_CASES,
    snapshot_cb=None,
) -> ProductBatchRunResult:
    return run_product_cases(
        rows,
        RUNTIME_POLICY,
        workers=workers,
        logfn=logfn,
        progress_cb=progress_cb,
        cancel_cb=cancel_cb,
        checkpoint_every_cases=checkpoint_every_cases,
        snapshot_cb=snapshot_cb,
    )


def _read_gui_cases(path: str | Path) -> tuple[dict[str, object], ...]:
    from panelsolver.app.gui_input_profile import (
        current_gui_input_profile,
        timed_call,
    )

    profile = current_gui_input_profile()
    frame = timed_call(
        profile,
        "GUI_ADAPTER",
        "read_case_table",
        read_cases,
        path,
    )
    return tuple(
        timed_call(
            profile,
            "GUI_ADAPTER",
            "dataframe_to_records",
            frame.to_dict,
            orient="records",
        )
    )


def _validate_gui_output(
    output_path: str | Path,
    input_path: str | Path,
    rows: Sequence[Mapping[str, object]],
) -> Path:
    return validate_results_output_path(output_path, input_path, rows)


def _resolve_velocity(row: Mapping[str, object]):
    return adapt_row(row).attitude.velocity_hat_stl


def _run_gui_cases(request: GuiRunRequest) -> GuiRunResult:
    result = run_and_write_product_cases(
        request.rows,
        RUNTIME_POLICY,
        request.output_path,
        workers=request.workers,
        logfn=request.log,
        progress_cb=request.progress,
        cancel_cb=request.cancel_requested,
        checkpoint_every_cases=request.checkpoint_every_cases,
        log_snapshots=True,
    )
    first = result.cases[0]
    return GuiRunResult(
        first_vtp_path=first.vtp_path or None,
        first_case_row=request.rows[0] if first.vtp_path else None,
    )


GUI_ADAPTERS = SolverGuiAdapters(
    read_cases=_read_gui_cases,
    build_case_signatures=build_primary_signatures,
    run_cases=_run_gui_cases,
    validate_output_path=_validate_gui_output,
    resolve_velocity_hat_stl=_resolve_velocity,
)

_PREFERRED_SCALARS = (
    "normal_traction_coeff",
    "tangential_traction_coeff",
    "shielded",
    "theta_deg",
    "area_m2",
    "center_x_stl_m",
    "center_y_stl_m",
    "center_z_stl_m",
    "stl_index",
)
_SCALAR_LABELS = {
    **COMMON_SCALAR_LABELS,
    "normal_traction_coeff": "Normal traction coeff.",
    "tangential_traction_coeff": "Tangential traction coeff.",
}
_DEFAULT_ADAPTERS = object()

_GUI_EXAMPLES = (
    ExampleDefinition("Basic", "fmf/basic.csv", ("geometry/plate.stl",)),
    ExampleDefinition(
        "Attitude Modes",
        "fmf/attitude_modes.csv",
        ("geometry/cube.stl",),
    ),
    ExampleDefinition(
        "Components",
        "fmf/components.csv",
        ("geometry/cube.stl", "geometry/plate_offset_x2.stl"),
    ),
    ExampleDefinition("Flow Modes", "fmf/flow_modes.csv", ("geometry/plate.stl",)),
    ExampleDefinition(
        "Shielding",
        "fmf/shielding.csv",
        ("geometry/double_plate.stl",),
    ),
)


def _present(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    return text


def _attitude_fields(row: Mapping[str, object]) -> tuple[tuple[str, object], ...]:
    attitude = (_present(row.get("attitude_input")) or "beta_tan").lower()
    alpha = row.get("alpha_deg")
    beta = row.get("beta_or_bank_deg")
    if attitude == "beta_sin":
        return (("alpha_t", alpha), ("beta_s", beta))
    if attitude == "bank":
        return (("alpha_i", alpha), ("phi", beta))
    return (("alpha_t", alpha), ("beta_t", beta))


def format_case(row: Mapping[str, object]) -> str:
    """Format the current FMF GUI overlay without evaluating physics."""
    fields: list[tuple[str, object]] = [("case_id", row.get("case_id"))]
    if _present(row.get("S")) and _present(row.get("Ti_K")):
        fields.extend((("mode", "A"), ("S", row.get("S")), ("Ti", row.get("Ti_K"))))
    elif _present(row.get("Mach")) and _present(row.get("Altitude_km")):
        fields.extend(
            (("mode", "B"), ("Mach", row.get("Mach")), ("Alt_km", row.get("Altitude_km")))
        )
    fields.append(("Tw", row.get("Tw_K")))
    fields.extend(_attitude_fields(row))
    fields.extend((("shield", row.get("shielding_on")), ("ray", row.get("ray_backend"))))
    return " | ".join(
        f"{name}={text}"
        for name, value in fields
        if (text := _present(value)) is not None
    )


def gui_spec(
    *,
    adapters: SolverGuiAdapters | None | object = _DEFAULT_ADAPTERS,
) -> SolverSpec:
    """Return the canonical FMF GUI composition."""
    selected_adapters = GUI_ADAPTERS if adapters is _DEFAULT_ADAPTERS else adapters
    return SolverSpec(
        product_id="fmf",
        model_id="sentman",
        window_title="Panel Solver — FMF",
        domain_name="FMF",
        case_columns=CSV_PROJECTION_POLICY.input_columns,
        preferred_scalars=_PREFERRED_SCALARS,
        scalar_labels=_SCALAR_LABELS,
        format_case=format_case,
        adapters=selected_adapters,  # type: ignore[arg-type]
        examples=_GUI_EXAMPLES,
    )


CANONICAL_CLI_POLICY = ProductCliPolicy(
    program="panelsolver fmf",
    description="Run the Sentman free-molecular-flow model from CSV/XLSX/XLSM input.",
    runtime_policy=RUNTIME_POLICY,
    read_cases=read_cases,
    validate_output_path=validate_results_output_path,
)


__all__ = (
    "CANONICAL_CLI_POLICY",
    "CASE_POLICY",
    "CASE_READER_POLICY",
    "CSV_PROJECTION_POLICY",
    "CSV_WRITE_POLICY",
    "DEFAULTS",
    "GUI_ADAPTERS",
    "INPUT_COLUMN_ORDER",
    "RUNTIME_POLICY",
    "InputValidationError",
    "ValidationIssue",
    "adapt_row",
    "build_primary_signatures",
    "format_case",
    "gui_spec",
    "project_csv",
    "read_cases",
    "run_cases",
    "validate_results_output_path",
    "write_csv",
)
