"""Headless artifact matching and scalar discovery for the shared viewer."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from numbers import Integral
from pathlib import Path

import numpy as np

from panelsolver.core import SignatureMatch, match_case_signature

from .solver_spec import ArtifactSignatureCandidates, CaseRow


class ArtifactLoadMode(str, Enum):
    """Whether an artifact is selected automatically or opened for inspection."""

    AUTOMATIC = "automatic"
    MANUAL = "manual"


class ArtifactViewStatus(str, Enum):
    """Model-neutral presentation status for one Viewer artifact surface."""

    EMPTY = "empty"
    CURRENT = "current"
    MISSING = "missing"
    WRITE_FAILED = "write_failed"
    STALE = "stale"
    MISMATCHED = "mismatched"
    READ_ERROR = "read_error"
    INVALID_DATA = "invalid_data"
    MANUAL_MATCHED = "manual_matched"
    MANUAL_UNMATCHED = "manual_unmatched"


@dataclass(frozen=True, slots=True)
class ArtifactViewState:
    """Immutable trusted facts needed to present Viewer artifact provenance."""

    status: ArtifactViewStatus
    path: Path | None = None
    case_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ArtifactViewStatus):
            raise TypeError("ArtifactViewState.status must be an ArtifactViewStatus")
        path = None
        if self.path is not None:
            try:
                path = Path(self.path).expanduser().resolve(strict=False)
            except TypeError as exc:
                raise TypeError("ArtifactViewState.path must be path-like") from exc
        case_id = self.case_id
        if case_id is not None:
            if not isinstance(case_id, str) or not case_id.strip():
                raise ValueError("ArtifactViewState.case_id must be non-empty")
            case_id = case_id.strip()

        if self.status is ArtifactViewStatus.EMPTY:
            if path is not None or case_id is not None:
                raise ValueError("empty artifact state cannot carry path or case_id")
        elif path is None:
            raise ValueError("non-empty artifact state requires a path")

        case_required = {
            ArtifactViewStatus.CURRENT,
            ArtifactViewStatus.MISSING,
            ArtifactViewStatus.STALE,
            ArtifactViewStatus.MISMATCHED,
            ArtifactViewStatus.MANUAL_MATCHED,
        }
        if self.status in case_required and case_id is None:
            raise ValueError(f"{self.status.value} artifact state requires case_id")
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "case_id", case_id)


@dataclass(frozen=True, slots=True)
class ArtifactCaseMatch:
    """Exact case-ID and primary/legacy signature comparison result."""

    case_id_matches: bool
    signature: SignatureMatch

    @property
    def matched(self) -> bool:
        return self.case_id_matches and self.signature.matched


_SHA256_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True)
class ScalarField:
    """One cell-aligned numeric scalar eligible for viewer coloring."""

    name: str
    dtype: np.dtype
    categorical: bool

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("ScalarField.name must be a non-empty string")
        object.__setattr__(self, "name", self.name.strip())
        try:
            dtype = np.dtype(self.dtype)
        except TypeError as exc:
            raise TypeError("ScalarField.dtype must be a NumPy dtype") from exc
        if dtype.kind not in "biuf":
            raise ValueError("ScalarField.dtype must be real numeric or boolean")
        object.__setattr__(self, "dtype", dtype)
        if not isinstance(self.categorical, bool):
            raise TypeError("ScalarField.categorical must be bool")


def _data_attribute(artifact: object, name: str) -> object | None:
    try:
        return getattr(artifact, name)
    except Exception:
        return None


def field_data_scalar(artifact: object, key: str) -> str | None:
    """Return a non-empty, single-valued field-data entry as text."""
    if not isinstance(key, str) or not key.strip():
        raise ValueError("key must be a non-empty string")
    field_data = _data_attribute(artifact, "field_data")
    if field_data is None:
        return None
    try:
        if key not in field_data:
            return None
        raw = np.asarray(field_data[key])
    except (KeyError, TypeError, ValueError):
        return None
    if raw.size != 1:
        return None
    try:
        text = str(raw.reshape(-1)[0]).strip()
    except Exception:
        return None
    return text or None


def match_artifact_case(
    artifact: object,
    row: CaseRow,
    candidates: ArtifactSignatureCandidates,
) -> ArtifactCaseMatch:
    """Match one artifact to one row without trusting case ID alone."""
    if not isinstance(row, Mapping):
        raise TypeError("row must be a mapping")
    if not isinstance(candidates, ArtifactSignatureCandidates):
        raise TypeError("candidates must be ArtifactSignatureCandidates")
    expected_case_id = str(row.get("case_id", "")).strip()
    actual_case_id = field_data_scalar(artifact, "case_id")
    stored_signature = field_data_scalar(artifact, "case_signature")
    signature = match_case_signature(
        stored_signature,
        candidates.primary,
        legacy_signatures=candidates.legacy_signatures,
    )
    return ArtifactCaseMatch(
        bool(expected_case_id) and actual_case_id == expected_case_id,
        signature,
    )


def automatic_artifact_view_state(
    artifact: object,
    row: CaseRow,
    candidates: ArtifactSignatureCandidates,
    path: str | Path,
) -> ArtifactViewState:
    """Classify automatic eligibility without changing the matching contract."""
    match = match_artifact_case(artifact, row, candidates)
    case_id = str(row.get("case_id", "")).strip()
    if not case_id:
        raise ValueError("row case_id must be non-empty")
    if match.matched:
        status = ArtifactViewStatus.CURRENT
    else:
        stored_signature = field_data_scalar(artifact, "case_signature")
        has_valid_stale_evidence = (
            match.case_id_matches
            and stored_signature is not None
            and _SHA256_DIGEST_PATTERN.fullmatch(stored_signature) is not None
        )
        status = (
            ArtifactViewStatus.STALE
            if has_valid_stale_evidence
            else ArtifactViewStatus.MISMATCHED
        )
    return ArtifactViewState(status, Path(path), case_id)


def manual_artifact_view_state(
    path: str | Path,
    matched_row: CaseRow | None,
) -> ArtifactViewState:
    """Describe a manual artifact without making unmatched inspection ineligible."""
    if matched_row is None:
        return ArtifactViewState(ArtifactViewStatus.MANUAL_UNMATCHED, Path(path))
    if not isinstance(matched_row, Mapping):
        raise TypeError("matched_row must be a mapping or None")
    case_id = str(matched_row.get("case_id", "")).strip()
    if not case_id:
        raise ValueError("matched_row case_id must be non-empty")
    return ArtifactViewState(
        ArtifactViewStatus.MANUAL_MATCHED,
        Path(path),
        case_id,
    )


def artifact_display_allowed(
    match: ArtifactCaseMatch | None,
    mode: ArtifactLoadMode,
) -> bool:
    """Allow manual inspection without requiring automatic signature eligibility."""
    if not isinstance(mode, ArtifactLoadMode):
        raise TypeError("mode must be an ArtifactLoadMode")
    if mode is ArtifactLoadMode.MANUAL:
        return True
    return match is not None and match.matched


def resolve_matching_case_row(
    artifact: object,
    rows: Sequence[CaseRow],
    build_candidates: Callable[[CaseRow], ArtifactSignatureCandidates],
) -> CaseRow | None:
    """Resolve a strict matching row, including duplicate case IDs, in input order."""
    if not callable(build_candidates):
        raise TypeError("build_candidates must be callable")
    actual_case_id = field_data_scalar(artifact, "case_id")
    if not actual_case_id:
        return None
    for row in rows:
        if not isinstance(row, Mapping):
            raise TypeError("rows must contain mappings")
        if str(row.get("case_id", "")).strip() != actual_case_id:
            continue
        if match_artifact_case(artifact, row, build_candidates(row)).matched:
            return row
    return None


def _eligible_scalar(name: str, value: object, *, n_cells: int) -> ScalarField | None:
    try:
        array = np.asarray(value)
    except (TypeError, ValueError):
        return None
    if array.shape != (n_cells,) or array.dtype.kind not in "biuf":
        return None
    if array.dtype.kind == "f" and not np.isfinite(array).all():
        return None
    return ScalarField(
        name=name,
        dtype=array.dtype,
        categorical=name == "shielded" or array.dtype.kind == "b",
    )


def discover_scalar_fields(
    cell_data: object,
    *,
    n_cells: int,
    preferred: Sequence[str] = (),
) -> tuple[ScalarField, ...]:
    """Discover stable cell scalars with preferred available fields first."""
    if not isinstance(n_cells, Integral) or isinstance(n_cells, bool) or n_cells <= 0:
        raise ValueError("n_cells must be a positive integer")
    n_cells = int(n_cells)
    if isinstance(preferred, str):
        raise TypeError("preferred must be an iterable of names, not a string")
    preferred_names = tuple(preferred)
    if any(not isinstance(name, str) or not name.strip() for name in preferred_names):
        raise ValueError("preferred must contain non-empty strings")
    if len(preferred_names) != len(set(preferred_names)):
        raise ValueError("preferred must contain unique names")

    discovered: dict[str, ScalarField] = {}
    try:
        items = cell_data.items()
    except AttributeError as exc:
        raise TypeError("cell_data must provide items()") from exc
    try:
        item_snapshot = tuple(items)
    except (TypeError, ValueError) as exc:
        raise TypeError("cell_data.items() must yield name/value pairs") from exc
    for name, value in item_snapshot:
        if not isinstance(name, str) or not name.strip():
            continue
        field = _eligible_scalar(name, value, n_cells=n_cells)
        if field is not None:
            discovered[name] = field

    ordered_names = [name for name in preferred_names if name in discovered]
    ordered_names.extend(name for name in discovered if name not in preferred_names)
    return tuple(discovered[name] for name in ordered_names)


def scalar_color_limits(field: ScalarField, values: object) -> tuple[float, float]:
    """Return the automatic viewer range, preserving categorical 0/1 semantics."""
    if not isinstance(field, ScalarField):
        raise TypeError("field must be a ScalarField")
    if field.categorical:
        return (0.0, 1.0)
    array = np.asarray(values)
    if array.ndim != 1 or array.size == 0 or array.dtype.kind not in "iuf":
        raise ValueError("values must be a non-empty real scalar array")
    if array.dtype.kind == "f" and not np.isfinite(array).all():
        raise ValueError("values must be finite")
    return (float(np.min(array)), float(np.max(array)))


__all__ = (
    "ArtifactCaseMatch",
    "ArtifactLoadMode",
    "ArtifactViewState",
    "ArtifactViewStatus",
    "ScalarField",
    "artifact_display_allowed",
    "automatic_artifact_view_state",
    "discover_scalar_fields",
    "field_data_scalar",
    "manual_artifact_view_state",
    "match_artifact_case",
    "resolve_matching_case_row",
    "scalar_color_limits",
)
