"""Durable CSV serialization and shared output-path validation."""

from __future__ import annotations

import csv
import errno
import io
import os
import tempfile
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from panelsolver.core.csv_projection import CsvProjection
from panelsolver.core.errors import ContractValueError

from .path_resolution import resolve_case_vtp_path, resolve_input_relative_path

CSV_ENCODING = "utf-8-sig"


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
) -> None:
    """Synchronize a complete CSV snapshot before replacing the previous file."""
    if not isinstance(projection, CsvProjection):
        raise ContractValueError("write_csv_atomic.projection", "must be CsvProjection")
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding=CSV_ENCODING,
            newline="",
            dir=out.parent,
            prefix=f".{out.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            _write_projection(handle, projection)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, out)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


class CsvAppendRollbackError(OSError):
    """A failed append could not restore the previous committed file length."""


def append_csv(out_path: str | Path, projection: CsvProjection) -> None:
    """Append complete rows, restoring the previous length on a caught failure.

    The caller must initialize this run's CSV first. A rollback failure makes
    further appends unsafe; an atomic final replacement can still be attempted.
    Abrupt process termination can leave an incomplete tail.
    """
    if not isinstance(projection, CsvProjection):
        raise ContractValueError("append_csv.projection", "must be CsvProjection")
    out = Path(out_path)
    with out.open(encoding=CSV_ENCODING, newline="") as reader:
        if tuple(next(csv.reader(reader), ())) != projection.columns:
            raise ValueError("checkpoint CSV columns do not match the pending results")
    # Serialize before touching the file, and encode without another BOM.
    text = io.StringIO(newline="")
    _write_projection(text, projection, header=False)
    pending = memoryview(text.getvalue().encode("utf-8"))
    with out.open("r+b", buffering=0) as handle:
        descriptor = handle.fileno()
        original_size = handle.seek(0, os.SEEK_END)
        try:
            while pending:
                written = os.write(descriptor, pending)
                if written <= 0:
                    raise OSError("checkpoint append made no write progress")
                pending = pending[written:]
            # Writes are unbuffered, so there is no Python buffer to flush.
            os.fsync(descriptor)
        except Exception as exc:
            try:
                os.ftruncate(descriptor, original_size)
                os.fsync(descriptor)
            except Exception as rollback_exc:
                raise CsvAppendRollbackError(
                    f"Checkpoint append failed: {exc}; rollback failed: "
                    f"{rollback_exc}. Further checkpoint appends are disabled; "
                    "the CSV tail may be incomplete."
                ) from exc
            raise


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


def _write_projection(
    handle: TextIO, projection: CsvProjection, *, header: bool = True
) -> None:
    writer = csv.writer(handle, lineterminator="\n")
    if header:
        writer.writerow(projection.columns)
    writer.writerows(
        tuple(row[name] for name in projection.columns) for row in projection.rows
    )


__all__ = (
    "CSV_ENCODING",
    "CsvAppendRollbackError",
    "append_csv",
    "paths_collide",
    "portable_path_key",
    "validate_csv_output_path",
    "validate_summary_output_path",
    "write_csv_atomic",
)
