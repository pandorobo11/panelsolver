"""Canonical Hypersonic application composition around its pressure models."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

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
    gui_run_result_from_batch,
    run_and_write_product_cases,
    run_product_cases,
)
from panelsolver.app.case_adapter import AdaptedCase, ProductCasePolicy, adapt_case_row
from panelsolver.app.case_io import (
    AddIssue,
    CaseReaderPolicy,
    InputValidationError,
    ValidationIssue,
    count_semicolon_entries,
    expand_component_values,
    normalize_optional_text,
    read_case_table,
    split_semicolon_tokens,
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
from panelsolver.models.hypersonic.selectors import (
    normalize_leeward_equation,
    normalize_windward_equation,
)

REQUIRED = (
    "case_id",
    "stl_path",
    "stl_scale_m_per_unit",
    "Mach",
    "gamma",
    "alpha_deg",
    "beta_or_bank_deg",
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
    "Mach",
    "gamma",
    "windward_eq",
    "leeward_eq",
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
    "Mach",
    "gamma",
    "alpha_deg",
    "beta_or_bank_deg",
    "ref_x_m",
    "ref_y_m",
    "ref_z_m",
    "Aref_m2",
    "Lref_Cl_m",
    "Lref_Cm_m",
    "Lref_Cn_m",
)
POSITIVE_COLUMNS = frozenset(
    {
        "stl_scale_m_per_unit",
        "Mach",
        "gamma",
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
    "windward_eq": "newtonian",
    "leeward_eq": "shield",
    "out_dir": "outputs",
}


def _validate_surface_equations(frame: pd.DataFrame, add_issue: AddIssue) -> None:
    for index in frame.index:
        component_count = max(count_semicolon_entries(frame.at[index, "stl_path"]), 1)
        try:
            windward = normalize_optional_text(
                frame.at[index, "windward_eq"],
                field="windward_eq",
                default="newtonian",
            )
            _, canonical = expand_component_values(
                windward,
                default_value="newtonian",
                resolver=normalize_windward_equation,
                component_count=component_count,
                field_name="windward_eq",
            )
            frame.at[index, "windward_eq"] = canonical
        except (TypeError, ValueError) as exc:
            add_issue(int(index), "windward_eq", str(exc))
            continue
        try:
            leeward = normalize_optional_text(
                frame.at[index, "leeward_eq"],
                field="leeward_eq",
                default="shield",
            )
            _, canonical = expand_component_values(
                leeward,
                default_value="shield",
                resolver=normalize_leeward_equation,
                component_count=component_count,
                field_name="leeward_eq",
            )
            frame.at[index, "leeward_eq"] = canonical
        except (TypeError, ValueError) as exc:
            add_issue(int(index), "leeward_eq", str(exc))


def _validate_rows(frame: pd.DataFrame, add_issue: AddIssue) -> None:
    _validate_surface_equations(frame, add_issue)
    for index in frame.index[frame["gamma"] <= 1.0]:
        add_issue(int(index), "gamma", "must be > 1.")
    for index in frame.index[frame["Mach"] <= 1.0]:
        windward = {
            token
            for token in split_semicolon_tokens(frame.at[index, "windward_eq"])
            if token
        }
        for equation in ("modified_newtonian", "tangent_wedge", "tangent_cone"):
            if equation in windward:
                add_issue(
                    int(index),
                    "Mach",
                    f"must be > 1 when windward_eq={equation}.",
                )
        if "prandtl_meyer" in {
            token
            for token in split_semicolon_tokens(frame.at[index, "leeward_eq"])
            if token
        }:
            add_issue(
                int(index),
                "Mach",
                "must be > 1 when leeward_eq=prandtl_meyer.",
            )


CASE_READER_POLICY = CaseReaderPolicy(
    required_columns=REQUIRED,
    input_columns=INPUT_COLUMN_ORDER,
    numeric_required=NUMERIC_REQUIRED,
    numeric_optional=(),
    positive_columns=POSITIVE_COLUMNS,
    defaults=DEFAULTS,
    validate_rows=_validate_rows,
    required_numeric_message_style="finite",
    keep_default_na=False,
    fill_defaults_by_presence=True,
)


def read_cases(path: str | Path) -> pd.DataFrame:
    """Read and validate the current Hypersonic case-table contract."""
    return read_case_table(path, CASE_READER_POLICY)


def _model_payload(row: Mapping[str, object]) -> Mapping[str, object]:
    return {
        "Mach": float(row["Mach"]),
        "gamma": float(row["gamma"]),
        "windward_eq": str(row.get("windward_eq", "newtonian")),
        "leeward_eq": str(row.get("leeward_eq", "shield")),
    }


CASE_POLICY = ProductCasePolicy(
    product_id="hypersonic",
    model_id="hypersonic",
    legacy_env_prefix="NEWTSOLVER",
    mesh_validation_policy=MeshValidationPolicy.STRICT,
    model_payload=_model_payload,
)


def adapt_row(
    row: Mapping[str, object],
    *,
    registry: ModelRegistry | None = None,
) -> AdaptedCase:
    """Adapt one normalized Hypersonic row to the shared execution request."""
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
    case_rows: Iterable[Mapping[str, object]],
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
        vtp_field_data={
            "windward_eq_used": str(metadata["windward_eq"]),
            "leeward_eq_used": str(metadata["leeward_eq"]),
        }
    )


RUNTIME_POLICY = ProductRuntimePolicy(
    product_id="hypersonic",
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
    return tuple(read_cases(path).to_dict(orient="records"))


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
    return gui_run_result_from_batch(request, result)


GUI_ADAPTERS = SolverGuiAdapters(
    read_cases=_read_gui_cases,
    build_case_signatures=build_primary_signatures,
    run_cases=_run_gui_cases,
    validate_output_path=_validate_gui_output,
    resolve_velocity_hat_stl=_resolve_velocity,
)

_PREFERRED_SCALARS = (
    "cp",
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
    "cp": "Cp",
}
_DEFAULT_ADAPTERS = object()

_GUI_EXAMPLES = (
    ExampleDefinition(
        "Basic",
        "hypersonic/basic.csv",
        ("geometry/plate.stl",),
    ),
    ExampleDefinition(
        "Attitude Modes",
        "hypersonic/attitude_modes.csv",
        ("geometry/cube.stl",),
    ),
    ExampleDefinition(
        "Components",
        "hypersonic/components.csv",
        ("geometry/cube.stl", "geometry/plate_offset_x2.stl"),
    ),
    ExampleDefinition(
        "Pressure Models",
        "hypersonic/pressure_models.csv",
        ("geometry/plate.stl", "geometry/cube.stl"),
    ),
    ExampleDefinition(
        "Shielding",
        "hypersonic/shielding.csv",
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
    """Format the current Hypersonic GUI overlay without evaluating physics."""
    fields: list[tuple[str, object]] = [
        ("case_id", row.get("case_id")),
        ("Mach", row.get("Mach")),
        ("gamma", row.get("gamma")),
        ("w_eq", row.get("windward_eq")),
        ("l_eq", row.get("leeward_eq")),
    ]
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
    """Return the canonical Hypersonic GUI composition."""
    selected_adapters = GUI_ADAPTERS if adapters is _DEFAULT_ADAPTERS else adapters
    return SolverSpec(
        product_id="hypersonic",
        model_id="hypersonic",
        window_title="Panel Solver — Hypersonic",
        domain_name="Hypersonic",
        case_columns=CSV_PROJECTION_POLICY.input_columns,
        preferred_scalars=_PREFERRED_SCALARS,
        scalar_labels=_SCALAR_LABELS,
        format_case=format_case,
        adapters=selected_adapters,  # type: ignore[arg-type]
        examples=_GUI_EXAMPLES,
    )


CANONICAL_CLI_POLICY = ProductCliPolicy(
    program="panelsolver hypersonic",
    description="Run hypersonic panel models from CSV/XLSX/XLSM input.",
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
