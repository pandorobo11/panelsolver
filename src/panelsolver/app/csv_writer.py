"""Policy-driven atomic CSV serialization for compatibility adapters."""

from __future__ import annotations

import csv
import errno
import os
import tempfile
import unicodedata
import uuid
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TextIO

from panelsolver.core.csv_projection import CsvProjection
from panelsolver.core.errors import ContractValueError

from .path_resolution import resolve_case_vtp_path, resolve_input_relative_path

CSV_ENCODING = "utf-8-sig"


class TempNameStyle(str, Enum):
    """Legacy same-directory temporary-file naming strategies."""

    NAMED_RANDOM = "named_random"
    UUID = "uuid"


@dataclass(frozen=True, slots=True)
class AtomicCsvWritePolicy:
    """Explicit temporary-file and durability behavior for one product."""

    temp_name_style: TempNameStyle
    fsync_before_replace: bool

    def __post_init__(self) -> None:
        if not isinstance(self.temp_name_style, TempNameStyle):
            raise ContractValueError(
                "AtomicCsvWritePolicy.temp_name_style",
                "must be a TempNameStyle",
            )
        if not isinstance(self.fsync_before_replace, bool):
            raise ContractValueError(
                "AtomicCsvWritePolicy.fsync_before_replace",
                "must be a boolean",
            )


DURABLE_CSV_WRITE_POLICY = AtomicCsvWritePolicy(
    temp_name_style=TempNameStyle.NAMED_RANDOM,
    fsync_before_replace=True,
)


@dataclass(frozen=True, slots=True)
class _CollisionPath:
    path: Path
    role: str
    case_id: str | None = None
    is_output: bool = False


def _resolved_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve(strict=False)


def _portable_component(component: str) -> str:
    return unicodedata.normalize("NFC", component).casefold()


def _portable_key_from_resolved(path: Path) -> tuple[str, tuple[str, ...]]:
    anchor = path.anchor
    parts = path.parts
    if anchor and parts and parts[0] == anchor:
        parts = parts[1:]
    return (
        _portable_component(anchor),
        tuple(_portable_component(part) for part in parts),
    )


def portable_path_key(path: str | Path) -> tuple[str, tuple[str, ...]]:
    """Return a conservative casefolded NFC key with structural components."""
    return _portable_key_from_resolved(_resolved_path(path))


def _same_existing_file(first: Path, second: Path) -> bool:
    try:
        return os.path.samefile(first, second)
    except FileNotFoundError:
        return False
    except OSError as exc:
        if exc.errno in {errno.ENOENT, errno.ENOTDIR}:
            return False
        raise


def paths_collide(first: str | Path, second: str | Path) -> bool:
    """Return whether paths collide portably or alias one existing file."""
    first_resolved = _resolved_path(first)
    second_resolved = _resolved_path(second)
    if _portable_key_from_resolved(first_resolved) == _portable_key_from_resolved(
        second_resolved
    ):
        return True
    return _same_existing_file(first_resolved, second_resolved)


def _existing_file_identity(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno in {errno.ENOENT, errno.ENOTDIR}:
            return None
        raise
    return stat.st_dev, stat.st_ino


def _describe_collision_path(candidate: _CollisionPath) -> str:
    case = f" (case_id={candidate.case_id!r})" if candidate.case_id else ""
    return f"{candidate.role} path '{candidate.path}'{case}"


def _raise_output_collision(first: _CollisionPath, second: _CollisionPath) -> None:
    raise ValueError(
        "Output path collision with protected path: "
        f"{_describe_collision_path(first)} collides with "
        f"{_describe_collision_path(second)}. Change one of these paths."
    )


def _validate_no_output_collisions(candidates: Iterable[_CollisionPath]) -> None:
    portable_seen: dict[tuple[str, tuple[str, ...]], _CollisionPath] = {}
    portable_outputs: dict[tuple[str, tuple[str, ...]], _CollisionPath] = {}
    identity_seen: dict[tuple[int, int], tuple[_CollisionPath, Path]] = {}
    identity_outputs: dict[tuple[int, int], tuple[_CollisionPath, Path]] = {}

    for candidate in candidates:
        resolved = _resolved_path(candidate.path)
        key = _portable_key_from_resolved(resolved)
        portable_match = (
            portable_seen.get(key) if candidate.is_output else portable_outputs.get(key)
        )
        if portable_match is not None:
            _raise_output_collision(portable_match, candidate)

        identity = _existing_file_identity(resolved)
        if identity is not None:
            identity_match = (
                identity_seen.get(identity)
                if candidate.is_output
                else identity_outputs.get(identity)
            )
            if identity_match is not None:
                previous, previous_resolved = identity_match
                if _same_existing_file(previous_resolved, resolved):
                    _raise_output_collision(previous, candidate)

        portable_seen.setdefault(key, candidate)
        if candidate.is_output:
            portable_outputs.setdefault(key, candidate)
        if identity is not None:
            identity_seen.setdefault(identity, (candidate, resolved))
            if candidate.is_output:
                identity_outputs.setdefault(identity, (candidate, resolved))


def write_csv_atomic(
    out_path: str | Path,
    projection: CsvProjection,
    policy: AtomicCsvWritePolicy,
) -> None:
    """Write a complete semantic CSV snapshot using the selected legacy policy."""
    if not isinstance(projection, CsvProjection):
        raise ContractValueError("write_csv_atomic.projection", "must be CsvProjection")
    if not isinstance(policy, AtomicCsvWritePolicy):
        raise ContractValueError(
            "write_csv_atomic.policy",
            "must be AtomicCsvWritePolicy",
        )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with _temporary_csv_file(out, policy.temp_name_style) as (handle, created_path):
            temp_path = created_path
            _write_projection(handle, projection)
            if policy.fsync_before_replace:
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(temp_path, out)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@contextmanager
def _temporary_csv_file(
    out: Path,
    style: TempNameStyle,
) -> Iterator[tuple[TextIO, Path]]:
    if style is TempNameStyle.NAMED_RANDOM:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=CSV_ENCODING,
            newline="",
            dir=out.parent,
            prefix=f".{out.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            yield handle, Path(handle.name)
        return
    temp_path = out.with_name(f".{out.name}.{uuid.uuid4().hex}.tmp")
    with temp_path.open("w", encoding=CSV_ENCODING, newline="") as handle:
        yield handle, temp_path


def validate_csv_output_path(
    out_path: str | Path,
    protected_paths: Iterable[str | Path],
) -> Path:
    """Resolve and reject an output path against an adapter-defined protected set."""
    out = Path(out_path)
    _validate_no_output_collisions(
        (
            _CollisionPath(out, "output", is_output=True),
            *(_CollisionPath(Path(path), "protected") for path in protected_paths),
        )
    )
    return _resolved_path(out)


def validate_summary_output_path(
    out_path: str | Path,
    input_path: str | Path,
    case_rows: Iterable[Mapping[str, object]],
) -> Path:
    """Reject a summary path that could destroy any input or planned artifact."""
    candidates = [
        _CollisionPath(Path(out_path), "summary", is_output=True),
        _CollisionPath(Path(input_path), "input"),
    ]
    for row in case_rows:
        case_id = str(row.get("case_id", "")).strip()
        for raw_stl in str(row.get("stl_path", "")).split(";"):
            if raw_stl.strip():
                candidates.append(
                    _CollisionPath(
                        resolve_input_relative_path(raw_stl.strip(), input_path),
                        "STL",
                        case_id=case_id,
                    )
                )
        if case_id:
            candidates.append(
                _CollisionPath(
                    resolve_case_vtp_path(row, input_path),
                    "planned VTP",
                    case_id=case_id,
                    is_output=True,
                )
            )
    _validate_no_output_collisions(candidates)
    return _resolved_path(out_path)


def _write_projection(handle: TextIO, projection: CsvProjection) -> None:
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(projection.columns)
    writer.writerows(
        tuple(row[name] for name in projection.columns) for row in projection.rows
    )


__all__ = (
    "CSV_ENCODING",
    "DURABLE_CSV_WRITE_POLICY",
    "AtomicCsvWritePolicy",
    "TempNameStyle",
    "paths_collide",
    "portable_path_key",
    "validate_csv_output_path",
    "validate_summary_output_path",
    "write_csv_atomic",
)
