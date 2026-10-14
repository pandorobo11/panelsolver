"""Retained ordinary-run Summary CSV and safe repeated export."""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from panelsolver.core import CsvProjection

from .csv_writer import validate_csv_output_path, write_csv_atomic
from .path_resolution import resolve_case_vtp_path, resolve_input_relative_path
from .solver_spec import CaseRow


def summary_protected_paths(
    input_path: Path | None, rows: Sequence[CaseRow]
) -> tuple[Path, ...]:
    """Protect every loaded case's inputs and planned VTP, selected or not."""
    if input_path is None:
        return ()
    paths = [input_path]
    for row in rows:
        for stl in str(row.get("stl_path", "")).split(";"):
            if stl.strip():
                paths.append(resolve_input_relative_path(stl.strip(), input_path))
        if str(row.get("case_id", "")).strip():
            paths.append(resolve_case_vtp_path(row, input_path))
    # Keep the original spelling as well as the current symlink target.
    return tuple(dict.fromkeys(p for path in paths for p in (path, path.resolve())))


@dataclass(frozen=True, slots=True)
class SummaryCsvSnapshot:
    csv: CsvProjection
    protected_paths: tuple[Path, ...]
    output_path: Path
    input_name: str
    case_count: int
    other_output_errors: bool


def write_summary_snapshot(
    path: Path,
    snapshot: SummaryCsvSnapshot,
    current_protected_paths: tuple[Path, ...],
) -> Path:
    output = validate_csv_output_path(
        path, (*snapshot.protected_paths, *current_protected_paths)
    )
    write_csv_atomic(output, snapshot.csv)
    return output
