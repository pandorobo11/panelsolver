"""Structured status for artifact output independent of case computation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class OutputKind(str, Enum):
    """User-visible output whose production failed."""

    VTP = "vtp"
    SUMMARY_CSV = "summary_csv"
    OUTPUT_DIRECTORY = "output_directory"


class OutputPhase(str, Enum):
    """Output lifecycle phase where an issue occurred."""

    PREPARE = "prepare"
    WRITE = "write"
    CHECKPOINT = "checkpoint"
    FINAL = "final"


@dataclass(frozen=True, slots=True)
class OutputIssue:
    """One non-computational output failure retained in a run result."""

    kind: OutputKind
    phase: OutputPhase
    path: str
    message: str
    case_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, OutputKind):
            raise TypeError("OutputIssue.kind must be an OutputKind")
        if not isinstance(self.phase, OutputPhase):
            raise TypeError("OutputIssue.phase must be an OutputPhase")
        raw_path = str(self.path).strip()
        message = str(self.message).strip()
        if not raw_path:
            raise ValueError("OutputIssue.path must not be empty")
        if not message:
            raise ValueError("OutputIssue.message must not be empty")
        case_id = None if self.case_id is None else str(self.case_id)
        object.__setattr__(self, "path", str(Path(raw_path)))
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "case_id", case_id)


class OutputFailuresError(RuntimeError):
    """CLI-facing failure raised after completed calculations had output issues."""

    def __init__(self, issues: tuple[OutputIssue, ...]) -> None:
        values = tuple(issues)
        if not values or any(not isinstance(issue, OutputIssue) for issue in values):
            raise TypeError("issues must contain OutputIssue values")
        self.issues = values
        super().__init__(
            f"Calculations completed, but {len(values)} output error(s) occurred."
        )


__all__ = (
    "OutputFailuresError",
    "OutputIssue",
    "OutputKind",
    "OutputPhase",
)
