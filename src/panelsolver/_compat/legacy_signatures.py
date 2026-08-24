"""Opaque pinned signature reconstruction owned by compatibility adapters."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from panelsolver.app.case_io import is_filled, split_semicolon_tokens
from panelsolver.app.solver_spec import ArtifactSignatureCandidates
from panelsolver.core import CaseSignature

type LegacyPayloadAdapter = Callable[
    [dict[str, object], Mapping[str, object], tuple[str, ...]],
    None,
]


@dataclass(frozen=True, slots=True)
class LegacySignaturePolicy:
    """Exact product-specific envelope choices around shared hashing mechanics."""

    keys: tuple[str, ...]
    numeric_keys: frozenset[str]
    compatibility_version: str
    file_identity_style: str
    adapt_payload: LegacyPayloadAdapter
    signature_schema_version: int | None = None

    def __post_init__(self) -> None:
        if self.file_identity_style not in {"fmf", "newtsolver"}:
            raise ValueError("file_identity_style must be 'fmf' or 'newtsolver'")
        if not self.compatibility_version:
            raise ValueError("compatibility_version must not be empty")
        if not callable(self.adapt_payload):
            raise TypeError("adapt_payload must be callable")


def _normalized_value(name: str, value: object, numeric_keys: frozenset[str]):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if name in numeric_keys:
        try:
            return float(value)
        except Exception:
            return str(value)
    return str(value)


def _file_identity(raw_path: str, style: str) -> dict[str, object]:
    path = Path(raw_path).expanduser()
    if style == "fmf":
        resolved = path.resolve()
        try:
            stat = resolved.stat()
        except OSError as exc:
            return {"path": str(resolved), "error": type(exc).__name__}
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        return {"path": str(resolved), "size": int(stat.st_size), "sha256": digest}
    try:
        resolved = path.resolve()
        content = resolved.read_bytes()
        return {
            "path": str(resolved),
            "size": resolved.stat().st_size,
            "sha256": hashlib.sha256(content).hexdigest(),
        }
    except OSError as exc:
        return {"path": str(path), "unavailable": type(exc).__name__}


def build_legacy_case_signature(
    row: Mapping[str, object],
    policy: LegacySignaturePolicy,
) -> str:
    """Rebuild one pinned legacy hash without interpreting it in core."""
    if not isinstance(row, Mapping):
        raise TypeError("row must be a mapping")
    if not isinstance(policy, LegacySignaturePolicy):
        raise TypeError("policy must be a LegacySignaturePolicy")
    data = {
        name: _normalized_value(name, row.get(name), policy.numeric_keys)
        for name in policy.keys
    }
    paths = tuple(
        token for token in split_semicolon_tokens(row.get("stl_path")) if token
    )
    if policy.file_identity_style == "fmf":
        data["signature_schema_version"] = policy.signature_schema_version
        data["solver_version"] = policy.compatibility_version
        data["stl_fingerprints"] = [
            _file_identity(path, policy.file_identity_style) for path in paths
        ]
    else:
        data["stl_path"] = ";".join(paths)
        data["stl_files"] = [
            _file_identity(path, policy.file_identity_style) for path in paths
        ]
        data["solver_version"] = policy.compatibility_version
    policy.adapt_payload(data, row, paths)
    payload = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_legacy_signature_candidates(
    row: Mapping[str, object],
    *,
    defaults: Mapping[str, object],
    policy: LegacySignaturePolicy,
) -> tuple[str, ...]:
    """Return direct-row then default-normalized legacy signature candidates."""
    direct = build_legacy_case_signature(row, policy)
    normalized = dict(row)
    for name, default in defaults.items():
        if not is_filled(normalized.get(name)):
            normalized[name] = default
    normalized_digest = build_legacy_case_signature(normalized, policy)
    return (direct,) if direct == normalized_digest else (direct, normalized_digest)


def build_artifact_signature_candidates(
    row: Mapping[str, object],
    *,
    primary: CaseSignature,
    defaults: Mapping[str, object],
    policy: LegacySignaturePolicy,
) -> ArtifactSignatureCandidates:
    """Combine the canonical signature with ordered opaque legacy candidates."""
    legacy = build_legacy_signature_candidates(
        row,
        defaults=defaults,
        policy=policy,
    )
    return ArtifactSignatureCandidates(primary, legacy)


__all__ = (
    "LegacyPayloadAdapter",
    "LegacySignaturePolicy",
    "build_artifact_signature_candidates",
    "build_legacy_case_signature",
    "build_legacy_signature_candidates",
)
