"""Canonical numerical case signatures and legacy-match precedence."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from ._validation import freeze_payload, nonempty_text
from .contracts import CommonCasePayload
from .errors import PanelSolverError
from .shielding import ResolvedShieldingConfig

CASE_SIGNATURE_SCHEMA_NAME = "panelsolver.case"
CASE_SIGNATURE_SCHEMA_VERSION = 1
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class SignatureError(PanelSolverError, ValueError):
    """A signature envelope or candidate violates the canonical schema."""


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def canonical_json(value: Mapping[str, object]) -> str:
    """Validate and serialize a JSON-shaped mapping deterministically."""
    try:
        frozen = freeze_payload(value, field="signature envelope")
        return json.dumps(
            _thaw_json(frozen),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except PanelSolverError as exc:
        raise SignatureError(str(exc)) from exc


def _validate_digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise SignatureError(f"{field} must be a lowercase SHA-256 hex digest.")
    return value


@dataclass(frozen=True, slots=True)
class CaseSignature:
    """Validated canonical envelope together with its SHA-256 digest."""

    digest: str
    canonical_payload: str
    envelope: Mapping[str, object]

    def __post_init__(self) -> None:
        digest = _validate_digest(self.digest, field="digest")
        if not isinstance(self.envelope, Mapping):
            raise SignatureError("envelope must be a mapping.")
        try:
            frozen = freeze_payload(self.envelope, field="signature envelope")
        except PanelSolverError as exc:
            raise SignatureError(str(exc)) from exc
        expected_payload = canonical_json(frozen)
        if self.canonical_payload != expected_payload:
            raise SignatureError("canonical_payload does not encode envelope.")
        expected_digest = hashlib.sha256(expected_payload.encode("utf-8")).hexdigest()
        if digest != expected_digest:
            raise SignatureError("digest does not match canonical_payload.")
        object.__setattr__(self, "digest", digest)
        object.__setattr__(self, "envelope", frozen)


def _common_case_envelope(case: CommonCasePayload) -> dict[str, object]:
    return {
        "case_id": case.case_id,
        "Aref_m2": case.Aref_m2,
        "moment_reference_stl_m": case.moment_reference_stl_m.tolist(),
        "Lref_Cl_m": case.Lref_Cl_m,
        "Lref_Cm_m": case.Lref_Cm_m,
        "Lref_Cn_m": case.Lref_Cn_m,
        "alpha_t_deg": case.alpha_t_deg,
        "beta_t_deg": case.beta_t_deg,
    }


def _shielding_envelope(config: ResolvedShieldingConfig) -> dict[str, object]:
    if not isinstance(config, ResolvedShieldingConfig):
        raise TypeError("shielding_config must be a ResolvedShieldingConfig instance")
    return {
        "algorithm_version": config.algorithm_version,
        "enabled": config.enabled,
        "requested_backend": config.requested_backend,
        "effective_backend": config.effective_backend,
        "batch_size": config.batch_size,
    }


def build_case_signature(
    *,
    geometry_fingerprint: str,
    common_case: CommonCasePayload,
    model_id: str,
    model_algorithm_version: str,
    model_case_payload: Mapping[str, object],
    shielding_config: ResolvedShieldingConfig,
) -> CaseSignature:
    """Build the exact canonical signature envelope defined by ADR 0005."""
    geometry_digest = _validate_digest(
        geometry_fingerprint,
        field="geometry_fingerprint",
    )
    if not isinstance(common_case, CommonCasePayload):
        raise TypeError("common_case must be a CommonCasePayload instance")
    try:
        validated_model_id = nonempty_text(model_id, field="model_id")
        validated_algorithm = nonempty_text(
            model_algorithm_version,
            field="model_algorithm_version",
        )
        frozen_model_case = freeze_payload(
            model_case_payload,
            field="model_case_payload",
        )
    except PanelSolverError as exc:
        raise SignatureError(str(exc)) from exc

    envelope = {
        "schema": {
            "name": CASE_SIGNATURE_SCHEMA_NAME,
            "version": CASE_SIGNATURE_SCHEMA_VERSION,
        },
        "geometry": {"fingerprint_sha256": geometry_digest},
        "common_case": _common_case_envelope(common_case),
        "model": {
            "id": validated_model_id,
            "algorithm_version": validated_algorithm,
            "case": frozen_model_case,
        },
        "shielding": _shielding_envelope(shielding_config),
    }
    payload = canonical_json(envelope)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return CaseSignature(digest, payload, envelope)


class SignatureMatchKind(str, Enum):
    """Source that matched a stored artifact signature."""

    PRIMARY = "primary"
    LEGACY = "legacy"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class SignatureMatch:
    """Result of primary-first artifact signature matching."""

    kind: SignatureMatchKind
    legacy_index: int | None = None

    @property
    def matched(self) -> bool:
        return self.kind is not SignatureMatchKind.NONE


def match_case_signature(
    stored_signature: object,
    primary: CaseSignature,
    *,
    legacy_signatures: Sequence[str] = (),
) -> SignatureMatch:
    """Match a stored signature, preferring the canonical primary identity.

    Legacy signatures are opaque caller-supplied values. Core neither rebuilds
    nor normalizes product-specific legacy signature payloads.
    """
    if not isinstance(primary, CaseSignature):
        raise TypeError("primary must be a CaseSignature instance")
    validated_legacy = tuple(
        _validate_digest(value, field=f"legacy_signatures[{index}]")
        for index, value in enumerate(legacy_signatures)
    )
    if stored_signature == primary.digest:
        return SignatureMatch(SignatureMatchKind.PRIMARY)
    for index, candidate in enumerate(validated_legacy):
        if stored_signature == candidate:
            return SignatureMatch(SignatureMatchKind.LEGACY, index)
    return SignatureMatch(SignatureMatchKind.NONE)


__all__ = (
    "CASE_SIGNATURE_SCHEMA_NAME",
    "CASE_SIGNATURE_SCHEMA_VERSION",
    "CaseSignature",
    "SignatureError",
    "SignatureMatch",
    "SignatureMatchKind",
    "build_case_signature",
    "canonical_json",
    "match_case_signature",
)
