"""Headless artifact matching and scalar discovery for the shared viewer."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from numbers import Integral

import numpy as np

from panelsolver.core import SignatureMatch, match_case_signature

from .solver_spec import ArtifactSignatureCandidates, CaseRow


class ArtifactLoadMode(str, Enum):
    """Whether an artifact is selected automatically or opened for inspection."""

    AUTOMATIC = "automatic"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class ArtifactCaseMatch:
    """Exact case-ID and primary/legacy signature comparison result."""

    case_id_matches: bool
    signature: SignatureMatch

    @property
    def matched(self) -> bool:
        return self.case_id_matches and self.signature.matched


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
    "ScalarField",
    "artifact_display_allowed",
    "discover_scalar_fields",
    "field_data_scalar",
    "match_artifact_case",
    "resolve_matching_case_row",
    "scalar_color_limits",
)
