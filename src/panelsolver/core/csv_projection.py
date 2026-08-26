"""Ordered, model-neutral summary CSV projection."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from ._validation import FrozenMapping, integer_scalar, nonempty_text
from .contracts import CommonResults, IntegratedCoefficients
from .errors import ContractValueError

type CsvCell = None | bool | int | float | str

_CALCULATED_RESULT_COLUMNS = frozenset(
    {
        "alpha_t_deg_resolved",
        "beta_t_deg_resolved",
        "scope",
        "component_id",
        "component_stl_path",
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
    }
)
_TOTAL_ONLY_PATH_COLUMNS = ("vtp_path",)


@dataclass(frozen=True, slots=True)
class CsvProjectionPolicy:
    """Explicit ordered input and result columns for one product adapter."""

    input_columns: tuple[str, ...]
    result_columns: tuple[str, ...]

    def __post_init__(self) -> None:
        input_columns = _column_tuple(self.input_columns, field="input_columns")
        result_columns = _column_tuple(self.result_columns, field="result_columns")
        overlap = set(input_columns) & set(result_columns)
        if overlap:
            raise ContractValueError(
                "CsvProjectionPolicy.result_columns",
                f"must not overlap input columns {sorted(overlap)}",
            )
        object.__setattr__(self, "input_columns", input_columns)
        object.__setattr__(self, "result_columns", result_columns)


@dataclass(frozen=True, slots=True)
class CsvProjection:
    """Immutable ordered CSV columns and semantic row cells."""

    columns: tuple[str, ...]
    rows: tuple[Mapping[str, CsvCell], ...]

    def __post_init__(self) -> None:
        columns = _column_tuple(self.columns, field="CsvProjection.columns")
        try:
            raw_rows = tuple(self.rows)
        except TypeError as exc:
            raise ContractValueError(
                "CsvProjection.rows",
                "must be an iterable of row mappings",
            ) from exc
        if not raw_rows:
            raise ContractValueError(
                "CsvProjection.rows",
                "must contain at least one row",
            )
        rows: list[FrozenMapping[CsvCell]] = []
        for row_index, row in enumerate(raw_rows):
            if not isinstance(row, Mapping):
                raise ContractValueError(
                    f"CsvProjection.rows[{row_index}]",
                    "must be a mapping",
                )
            if tuple(row) != columns:
                raise ContractValueError(
                    f"CsvProjection.rows[{row_index}]",
                    "keys and key order must exactly match columns",
                )
            rows.append(
                FrozenMapping(
                    (
                        name,
                        _csv_cell(
                            row[name],
                            field=f"CsvProjection.rows[{row_index}].{name}",
                        ),
                    )
                    for name in columns
                )
            )
        object.__setattr__(self, "columns", columns)
        object.__setattr__(self, "rows", tuple(rows))


def project_summary_csv(
    input_row: Mapping[str, CsvCell],
    results: CommonResults,
    policy: CsvProjectionPolicy,
    *,
    run_values: Mapping[str, CsvCell],
    component_sources: Mapping[int, str] | None = None,
) -> CsvProjection:
    """Project one total row and ordered component rows using an explicit schema."""
    if not isinstance(results, CommonResults):
        raise ContractValueError("project_summary_csv.results", "must be CommonResults")
    if not isinstance(policy, CsvProjectionPolicy):
        raise ContractValueError(
            "project_summary_csv.policy",
            "must be CsvProjectionPolicy",
        )
    inputs = _cell_mapping(input_row, field="project_summary_csv.input_row")
    if inputs.get("case_id") != results.case.case_id:
        raise ContractValueError(
            "project_summary_csv.input_row.case_id",
            "must equal CommonResults.case.case_id",
        )

    ordered_inputs = tuple(name for name in policy.input_columns if name in inputs)
    input_extras = tuple(name for name in inputs if name not in policy.input_columns)
    input_columns = (*ordered_inputs, *input_extras)
    collisions = set(input_columns) & set(policy.result_columns)
    if collisions:
        raise ContractValueError(
            "project_summary_csv.input_row",
            f"extra input columns collide with result columns {sorted(collisions)}",
        )

    supplied = _cell_mapping(run_values, field="project_summary_csv.run_values")
    unexpected = set(supplied) - set(policy.result_columns)
    if unexpected:
        raise ContractValueError(
            "project_summary_csv.run_values",
            f"contains columns outside the product schema {sorted(unexpected)}",
        )
    calculated_overrides = set(supplied) & _CALCULATED_RESULT_COLUMNS
    if calculated_overrides:
        raise ContractValueError(
            "project_summary_csv.run_values",
            f"must not override calculated columns {sorted(calculated_overrides)}",
        )

    sources = _component_source_mapping(component_sources, results=results)
    total_values: dict[str, CsvCell] = dict(supplied)
    total_values.update(
        _calculated_row(
            results.total,
            alpha_t_deg=results.case.alpha_t_deg,
            beta_t_deg=results.case.beta_t_deg,
            scope="total",
            component_id=None,
            component_stl_path=None,
            faces=results.geometry.n_faces,
            shielded_faces=int(results.flow_state.shielded.sum()),
        )
    )
    projected_values = [total_values]
    if len(results.components) > 1:
        for component in results.components:
            component_values = dict(total_values)
            component_values.update(
                _calculated_row(
                    component.integrated,
                    alpha_t_deg=results.case.alpha_t_deg,
                    beta_t_deg=results.case.beta_t_deg,
                    scope="component",
                    component_id=component.component_id,
                    component_stl_path=sources[component.component_id],
                    faces=component.face_count,
                    shielded_faces=component.shielded_face_count,
                )
            )
            for name in _TOTAL_ONLY_PATH_COLUMNS:
                if name in policy.result_columns:
                    component_values[name] = None
            projected_values.append(component_values)

    columns = (*input_columns, *policy.result_columns)
    rows: list[dict[str, CsvCell]] = []
    for row_index, result_values in enumerate(projected_values):
        missing = [name for name in policy.result_columns if name not in result_values]
        if missing:
            raise ContractValueError(
                "project_summary_csv.run_values",
                f"row {row_index} is missing result columns {missing}",
            )
        rows.append(
            {
                **{name: inputs[name] for name in input_columns},
                **{name: result_values[name] for name in policy.result_columns},
            }
        )
    return CsvProjection(columns, tuple(rows))


def _calculated_row(
    integrated: IntegratedCoefficients,
    *,
    alpha_t_deg: float,
    beta_t_deg: float,
    scope: str,
    component_id: int | None,
    component_stl_path: str | None,
    faces: int,
    shielded_faces: int,
) -> dict[str, CsvCell]:
    return {
        "alpha_t_deg_resolved": alpha_t_deg,
        "beta_t_deg_resolved": beta_t_deg,
        "scope": scope,
        "component_id": component_id,
        "component_stl_path": component_stl_path,
        "CA": integrated.CA,
        "CY": integrated.CY,
        "CN": integrated.CN,
        "Cl": integrated.Cl,
        "Cm": integrated.Cm,
        "Cn": integrated.Cn,
        "CD": integrated.CD,
        "CL": integrated.CL,
        "faces": faces,
        "shielded_faces": shielded_faces,
    }


def _component_source_mapping(
    value: Mapping[int, str] | None,
    *,
    results: CommonResults,
) -> dict[int, str]:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise ContractValueError(
            "project_summary_csv.component_sources",
            "must be a mapping",
        )
    sources: dict[int, str] = {}
    for raw_id, raw_source in value.items():
        component_id = integer_scalar(
            raw_id,
            field="project_summary_csv.component_sources key",
            nonnegative=True,
        )
        if component_id in sources:
            raise ContractValueError(
                "project_summary_csv.component_sources",
                "component IDs must be unique",
            )
        sources[component_id] = nonempty_text(
            raw_source,
            field=f"project_summary_csv.component_sources[{component_id}]",
        )
    expected_ids = {component.component_id for component in results.components}
    unexpected = set(sources) - expected_ids
    if unexpected:
        raise ContractValueError(
            "project_summary_csv.component_sources",
            f"contains unknown component IDs {sorted(unexpected)}",
        )
    if len(results.components) > 1:
        missing = expected_ids - set(sources)
        if missing:
            raise ContractValueError(
                "project_summary_csv.component_sources",
                f"is missing component IDs {sorted(missing)}",
            )
    return sources


def _cell_mapping(
    value: Mapping[str, CsvCell],
    *,
    field: str,
) -> FrozenMapping[CsvCell]:
    if not isinstance(value, Mapping):
        raise ContractValueError(field, "must be a mapping")
    items: list[tuple[str, CsvCell]] = []
    for raw_name, raw_value in value.items():
        name = nonempty_text(raw_name, field=f"{field} key")
        items.append((name, _csv_cell(raw_value, field=f"{field}.{name}")))
    return FrozenMapping(items)


def _csv_cell(value: object, *, field: str) -> CsvCell:
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise ContractValueError(
        field,
        "must be a CSV scalar (null, boolean, integer, float, or string)",
    )


def _column_tuple(value: object, *, field: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise ContractValueError(field, "must be an iterable of column names")
    try:
        columns = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise ContractValueError(field, "must be an iterable of column names") from exc
    if not columns:
        raise ContractValueError(field, "must contain at least one column")
    validated = tuple(nonempty_text(name, field=f"{field} item") for name in columns)
    if len(validated) != len(set(validated)):
        raise ContractValueError(field, "must contain unique column names")
    return validated


__all__ = (
    "CsvCell",
    "CsvProjection",
    "CsvProjectionPolicy",
    "project_summary_csv",
)
