"""Private newtsolver command/GUI identity and legacy artifact matching."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from panelsolver._compat.legacy_signatures import (
    LegacySignaturePolicy,
    build_artifact_signature_candidates,
)
from panelsolver._compat.versions import NEWTSOLVER_COMPATIBILITY_VERSION
from panelsolver.app.case_io import expand_component_values
from panelsolver.app.solver_spec import (
    ArtifactSignatureCandidates,
    SolverGuiAdapters,
    SolverSpec,
)
from panelsolver.core import prepare_case_signature
from panelsolver.domains.hypersonic import DEFAULTS, GUI_ADAPTERS, adapt_row
from panelsolver.domains.hypersonic import gui_spec as canonical_gui_spec
from panelsolver.models import ModelRegistry
from panelsolver.models.hypersonic.selectors import (
    normalize_leeward_equation,
    normalize_windward_equation,
)

_SIGNATURE_KEYS = (
    "case_id",
    "stl_path",
    "stl_scale_m_per_unit",
    "Mach",
    "gamma",
    "windward_eq",
    "leeward_eq",
    "alpha_deg",
    "beta_or_bank_deg",
    "attitude_input",
    "ref_x_m",
    "ref_y_m",
    "ref_z_m",
    "Aref_m2",
    "Lref_Cl_m",
    "Lref_Cm_m",
    "Lref_Cn_m",
    "shielding_on",
    "ray_backend",
)
_NUMERIC_SIGNATURE_KEYS = frozenset(
    {
        "stl_scale_m_per_unit",
        "Mach",
        "gamma",
        "alpha_deg",
        "beta_or_bank_deg",
        "ref_x_m",
        "ref_y_m",
        "ref_z_m",
        "Aref_m2",
        "Lref_Cl_m",
        "Lref_Cm_m",
        "Lref_Cn_m",
        "shielding_on",
    }
)


def _canonical_or_raw(
    value: object,
    *,
    default: str,
    field: str,
    component_count: int,
    resolver,
) -> str:
    try:
        _, canonical = expand_component_values(
            value,
            default_value=default,
            resolver=resolver,
            component_count=component_count,
            field_name=field,
        )
        return canonical
    except Exception:
        raw = str(value or "").strip().lower()
        return raw or default


def _adapt_legacy_payload(
    data: dict[str, object],
    row: Mapping[str, object],
    paths: tuple[str, ...],
) -> None:
    component_count = max(len(paths), 1)
    data["windward_eq"] = _canonical_or_raw(
        row.get("windward_eq"),
        default="newtonian",
        field="windward_eq",
        component_count=component_count,
        resolver=normalize_windward_equation,
    )
    data["leeward_eq"] = _canonical_or_raw(
        row.get("leeward_eq"),
        default="shield",
        field="leeward_eq",
        component_count=component_count,
        resolver=normalize_leeward_equation,
    )


_LEGACY_SIGNATURE_POLICY = LegacySignaturePolicy(
    keys=_SIGNATURE_KEYS,
    numeric_keys=_NUMERIC_SIGNATURE_KEYS,
    compatibility_version=NEWTSOLVER_COMPATIBILITY_VERSION,
    file_identity_style="newtsolver",
    adapt_payload=_adapt_legacy_payload,
)
_DEFAULT_ADAPTERS = object()


def _build_artifact_signatures(
    row: Mapping[str, object],
    *,
    registry: ModelRegistry | None = None,
) -> ArtifactSignatureCandidates:
    primary = prepare_case_signature(adapt_row(row, registry=registry).request)
    return build_artifact_signature_candidates(
        row,
        primary=primary,
        defaults=DEFAULTS,
        policy=_LEGACY_SIGNATURE_POLICY,
    )


def _legacy_gui_spec(
    *,
    adapters: SolverGuiAdapters | None | object = _DEFAULT_ADAPTERS,
) -> SolverSpec:
    selected_adapters = adapters
    if adapters is _DEFAULT_ADAPTERS:
        selected_adapters = replace(
            GUI_ADAPTERS,
            build_case_signatures=_build_artifact_signatures,
        )
    return replace(
        canonical_gui_spec(adapters=selected_adapters),  # type: ignore[arg-type]
        product_id="newtsolver",
        window_title="newtsolver (GUI)",
    )
