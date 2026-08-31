"""Model-neutral configuration for the shared graphical application."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType

from panelsolver.core import CaseSignature, match_case_signature

from .examples import ExampleDefinition
from .output_status import OutputIssue
from .runtime import ProductBatchRunResult

type CaseRow = Mapping[str, object]
type ReadCasesCallback = Callable[[str | Path], Sequence[CaseRow]]
type LogCallback = Callable[[str], None]
type ProgressCallback = Callable[[int, int], None]
type CancelRequestedCallback = Callable[[], bool]
type ValidateOutputPathCallback = Callable[
    [str | Path, str | Path, Sequence[CaseRow]], Path
]
type ResolveVelocityCallback = Callable[[CaseRow], object]
type FormatCaseCallback = Callable[[CaseRow], str]


COMMON_SCALAR_LABELS: Mapping[str, str] = MappingProxyType(
    {
        "shielded": "Shielded",
        "theta_deg": "Theta [deg]",
        "area_m2": "Area [m^2]",
        "center_x_stl_m": "Center X [m]",
        "center_y_stl_m": "Center Y [m]",
        "center_z_stl_m": "Center Z [m]",
        "stl_index": "STL index",
    }
)


@dataclass(frozen=True, slots=True)
class GuiRunRequest:
    """Product-neutral execution request passed to one GUI adapter."""

    rows: tuple[CaseRow, ...]
    workers: int
    checkpoint_every_cases: int
    output_path: Path
    log: LogCallback
    progress: ProgressCallback
    cancel_requested: CancelRequestedCallback

    def __post_init__(self) -> None:
        rows = tuple(self.rows)
        if not rows:
            raise ValueError("GuiRunRequest.rows must not be empty")
        if any(not isinstance(row, Mapping) for row in rows):
            raise TypeError("GuiRunRequest.rows must contain mappings")
        if isinstance(self.workers, bool) or not isinstance(self.workers, int):
            raise TypeError("GuiRunRequest.workers must be an integer")
        if self.workers < 1:
            raise ValueError("GuiRunRequest.workers must be at least one")
        if isinstance(self.checkpoint_every_cases, bool) or not isinstance(
            self.checkpoint_every_cases, int
        ):
            raise TypeError("GuiRunRequest.checkpoint_every_cases must be an integer")
        if self.checkpoint_every_cases < 0:
            raise ValueError("GuiRunRequest.checkpoint_every_cases must be nonnegative")
        output_path = Path(self.output_path)
        for field_name in ("log", "progress", "cancel_requested"):
            if not callable(getattr(self, field_name)):
                raise TypeError(f"GuiRunRequest.{field_name} must be callable")
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "output_path", output_path)


@dataclass(frozen=True, slots=True)
class GuiRunResult:
    """Structured completion data separating calculation and output status."""

    first_vtp_path: Path | None = None
    first_case_row: CaseRow | None = None
    calculation_completed_cases: int = 0
    calculation_total_cases: int = 0
    summary_csv_saved: bool | None = None
    vtp_requested: int = 0
    vtp_saved: int = 0
    output_issues: tuple[OutputIssue, ...] = ()

    def __post_init__(self) -> None:
        if self.first_vtp_path is not None:
            object.__setattr__(self, "first_vtp_path", Path(self.first_vtp_path))
        if self.first_case_row is not None and not isinstance(
            self.first_case_row,
            Mapping,
        ):
            raise TypeError("GuiRunResult.first_case_row must be a mapping or None")
        for name in (
            "calculation_completed_cases",
            "calculation_total_cases",
            "vtp_requested",
            "vtp_saved",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"GuiRunResult.{name} must be an integer")
            if value < 0:
                raise ValueError(f"GuiRunResult.{name} must be nonnegative")
        if self.calculation_completed_cases > self.calculation_total_cases:
            raise ValueError("completed calculation count must not exceed total")
        if self.vtp_saved > self.vtp_requested:
            raise ValueError("saved VTP count must not exceed requested count")
        if self.summary_csv_saved is not None and not isinstance(
            self.summary_csv_saved, bool
        ):
            raise TypeError("GuiRunResult.summary_csv_saved must be a boolean or None")
        issues = tuple(self.output_issues)
        if any(not isinstance(issue, OutputIssue) for issue in issues):
            raise TypeError(
                "GuiRunResult.output_issues must contain OutputIssue values"
            )
        object.__setattr__(self, "output_issues", issues)


type RunCasesCallback = Callable[[GuiRunRequest], GuiRunResult]


def gui_run_result_from_batch(
    request: GuiRunRequest,
    result: ProductBatchRunResult,
) -> GuiRunResult:
    """Project common runtime output status onto the shared GUI contract."""
    if not isinstance(request, GuiRunRequest):
        raise TypeError("request must be a GuiRunRequest")
    if not isinstance(result, ProductBatchRunResult):
        raise TypeError("result must be a ProductBatchRunResult")
    first = result.cases[0]
    return GuiRunResult(
        first_vtp_path=first.vtp_path or None,
        first_case_row=request.rows[0] if first.vtp_path else None,
        calculation_completed_cases=len(result.cases),
        calculation_total_cases=len(request.rows),
        summary_csv_saved=result.summary_csv_saved,
        vtp_requested=sum(bool(int(row.get("save_vtp_on", 1))) for row in request.rows),
        vtp_saved=sum(bool(case.vtp_path) for case in result.cases),
        output_issues=result.output_issues,
    )


@dataclass(frozen=True, slots=True)
class ArtifactSignatureCandidates:
    """Canonical primary signature plus opaque product-specific legacy fallbacks."""

    primary: CaseSignature
    legacy_signatures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.primary, CaseSignature):
            raise TypeError(
                "ArtifactSignatureCandidates.primary must be a CaseSignature"
            )
        try:
            legacy = tuple(self.legacy_signatures)
        except TypeError as exc:
            raise TypeError(
                "ArtifactSignatureCandidates.legacy_signatures must be iterable"
            ) from exc
        match_case_signature(
            None,
            self.primary,
            legacy_signatures=legacy,
        )
        object.__setattr__(self, "legacy_signatures", legacy)


type BuildCaseSignaturesCallback = Callable[[CaseRow], ArtifactSignatureCandidates]


@dataclass(frozen=True, slots=True)
class SolverGuiAdapters:
    """Adapters supplying domain-specific behavior at the shared GUI boundary.

    The complete adapter set supplies case reading, signature construction,
    execution, output validation, and velocity-direction resolution while keeping
    shared widgets independent of compatibility frontends.
    """

    read_cases: ReadCasesCallback
    build_case_signatures: BuildCaseSignaturesCallback
    run_cases: RunCasesCallback
    validate_output_path: ValidateOutputPathCallback
    resolve_velocity_hat_stl: ResolveVelocityCallback

    def __post_init__(self) -> None:
        for field_name in (
            "read_cases",
            "build_case_signatures",
            "run_cases",
            "validate_output_path",
            "resolve_velocity_hat_stl",
        ):
            if not callable(getattr(self, field_name)):
                raise TypeError(f"SolverGuiAdapters.{field_name} must be callable")


def _nonempty_text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _unique_names(value: object, *, field: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise TypeError(f"{field} must be an iterable of names, not a string")
    try:
        iterator = iter(value)
    except TypeError as exc:
        raise TypeError(f"{field} must be an iterable of names") from exc
    names = tuple(_nonempty_text(item, field=f"{field} item") for item in iterator)
    if not names:
        raise ValueError(f"{field} must not be empty")
    if len(names) != len(set(names)):
        raise ValueError(f"{field} must contain unique names")
    return names


def _scalar_label_mapping(value: object) -> Mapping[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError("SolverSpec.scalar_labels must be a mapping")
    labels: dict[str, str] = {}
    for raw_name, raw_label in value.items():
        name = _nonempty_text(
            raw_name,
            field="SolverSpec.scalar_labels key",
        )
        label = _nonempty_text(
            raw_label,
            field=f"SolverSpec.scalar_labels.{name}",
        )
        if name in labels:
            raise ValueError(
                "SolverSpec.scalar_labels must contain unique internal names"
            )
        labels[name] = label
    if len(labels) != len(set(labels.values())):
        raise ValueError("SolverSpec.scalar_labels must contain unique labels")
    return MappingProxyType(labels)


class CaseColumnKind(str, Enum):
    """Model-neutral display category for one case-table column."""

    TEXT = "text"
    NUMERIC = "numeric"
    FLAG = "flag"


class CaseColumnWidthRole(str, Enum):
    """Model-neutral initial-width intent for one case-table column."""

    IDENTIFIER = "identifier"
    PATH = "path"
    COMPACT_NUMERIC = "compact_numeric"
    ENGINEERING_NUMERIC = "engineering_numeric"
    MODEL_TEXT = "model_text"
    ENUM_TEXT = "enum_text"
    FLAG = "flag"
    FALLBACK = "fallback"


@dataclass(frozen=True, slots=True)
class CaseColumnPresentation:
    """Immutable UI presentation intent for one internal column."""

    name: str
    label: str
    kind: CaseColumnKind
    width_role: CaseColumnWidthRole

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "name",
            _nonempty_text(self.name, field="CaseColumnPresentation.name"),
        )
        object.__setattr__(
            self,
            "label",
            _nonempty_text(self.label, field="CaseColumnPresentation.label"),
        )
        if not isinstance(self.kind, CaseColumnKind):
            raise TypeError("CaseColumnPresentation.kind must be a CaseColumnKind")
        if not isinstance(self.width_role, CaseColumnWidthRole):
            raise TypeError(
                "CaseColumnPresentation.width_role must be a CaseColumnWidthRole"
            )


def _case_column_presentations(value: object) -> tuple[CaseColumnPresentation, ...]:
    if isinstance(value, (str, bytes)):
        raise TypeError(
            "SolverSpec.case_column_presentations must be an iterable of metadata"
        )
    try:
        presentations = tuple(value)  # type: ignore[arg-type]
    except TypeError as exc:
        raise TypeError(
            "SolverSpec.case_column_presentations must be an iterable"
        ) from exc
    if not presentations:
        raise ValueError("SolverSpec.case_column_presentations must not be empty")
    if any(
        not isinstance(presentation, CaseColumnPresentation)
        for presentation in presentations
    ):
        raise TypeError(
            "SolverSpec.case_column_presentations must contain "
            "CaseColumnPresentation values"
        )
    names = tuple(presentation.name for presentation in presentations)
    if len(names) != len(set(names)):
        raise ValueError(
            "SolverSpec.case_column_presentations must contain unique internal names"
        )
    return presentations


@dataclass(frozen=True, slots=True)
class SolverSpec:
    """Identity and presentation policy consumed by every shared GUI widget."""

    product_id: str
    model_id: str
    window_title: str
    domain_name: str
    case_columns: tuple[str, ...]
    case_column_presentations: tuple[CaseColumnPresentation, ...]
    preferred_scalars: tuple[str, ...]
    scalar_labels: Mapping[str, str]
    format_case: FormatCaseCallback
    adapters: SolverGuiAdapters | None = None
    examples: tuple[ExampleDefinition, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "product_id",
            _nonempty_text(self.product_id, field="SolverSpec.product_id"),
        )
        object.__setattr__(
            self,
            "model_id",
            _nonempty_text(self.model_id, field="SolverSpec.model_id"),
        )
        object.__setattr__(
            self,
            "window_title",
            _nonempty_text(self.window_title, field="SolverSpec.window_title"),
        )
        object.__setattr__(
            self,
            "domain_name",
            _nonempty_text(self.domain_name, field="SolverSpec.domain_name"),
        )
        object.__setattr__(
            self,
            "case_columns",
            _unique_names(self.case_columns, field="SolverSpec.case_columns"),
        )
        if self.case_columns[0] != "case_id":
            raise ValueError("SolverSpec.case_columns must start with 'case_id'")
        case_column_presentations = _case_column_presentations(
            self.case_column_presentations
        )
        presentation_names = tuple(
            presentation.name for presentation in case_column_presentations
        )
        if presentation_names != self.case_columns:
            raise ValueError(
                "SolverSpec.case_column_presentations internal names must match "
                "SolverSpec.case_columns in order"
            )
        object.__setattr__(
            self,
            "case_column_presentations",
            case_column_presentations,
        )
        object.__setattr__(
            self,
            "preferred_scalars",
            _unique_names(
                self.preferred_scalars,
                field="SolverSpec.preferred_scalars",
            ),
        )
        scalar_labels = _scalar_label_mapping(self.scalar_labels)
        missing_labels = set(self.preferred_scalars) - set(scalar_labels)
        if missing_labels:
            raise ValueError(
                "SolverSpec.scalar_labels must label every preferred scalar: "
                f"{sorted(missing_labels)}"
            )
        object.__setattr__(self, "scalar_labels", scalar_labels)
        if not callable(self.format_case):
            raise TypeError("SolverSpec.format_case must be callable")
        if self.adapters is not None and not isinstance(
            self.adapters,
            SolverGuiAdapters,
        ):
            raise TypeError("SolverSpec.adapters must be SolverGuiAdapters or None")
        try:
            examples = tuple(self.examples)
        except TypeError as exc:
            raise TypeError("SolverSpec.examples must be iterable") from exc
        if any(not isinstance(example, ExampleDefinition) for example in examples):
            raise TypeError("SolverSpec.examples must contain ExampleDefinition values")
        labels = tuple(example.label for example in examples)
        inputs = tuple(example.input_resource for example in examples)
        if len(labels) != len(set(labels)) or len(inputs) != len(set(inputs)):
            raise ValueError("SolverSpec.examples must have unique labels and inputs")
        object.__setattr__(self, "examples", examples)


__all__ = (
    "COMMON_SCALAR_LABELS",
    "ArtifactSignatureCandidates",
    "BuildCaseSignaturesCallback",
    "CancelRequestedCallback",
    "CaseColumnKind",
    "CaseColumnPresentation",
    "CaseColumnWidthRole",
    "CaseRow",
    "ExampleDefinition",
    "FormatCaseCallback",
    "GuiRunRequest",
    "GuiRunResult",
    "LogCallback",
    "ProgressCallback",
    "ReadCasesCallback",
    "ResolveVelocityCallback",
    "RunCasesCallback",
    "SolverGuiAdapters",
    "SolverSpec",
    "ValidateOutputPathCallback",
    "gui_run_result_from_batch",
)
