"""Private FMF command/GUI identity and legacy artifact matching."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from panelsolver._compat.legacy_signatures import (
    LegacySignaturePolicy,
    build_artifact_signature_candidates,
)
from panelsolver._compat.versions import FMFSOLVER_COMPATIBILITY_VERSION
from panelsolver.app.solver_spec import (
    ArtifactSignatureCandidates,
    SolverGuiAdapters,
    SolverSpec,
)
from panelsolver.core import prepare_case_signature
from panelsolver.domains.fmf import DEFAULTS, GUI_ADAPTERS, adapt_row
from panelsolver.domains.fmf import gui_spec as canonical_gui_spec
from panelsolver.models import ModelRegistry

_SIGNATURE_KEYS = (
    "case_id",
    "stl_path",
    "stl_scale_m_per_unit",
    "alpha_deg",
    "beta_or_bank_deg",
    "attitude_input",
    "Tw_K",
    "ref_x_m",
    "ref_y_m",
    "ref_z_m",
    "Aref_m2",
    "Lref_Cl_m",
    "Lref_Cm_m",
    "Lref_Cn_m",
    "S",
    "Ti_K",
    "Mach",
    "Altitude_km",
    "shielding_on",
    "ray_backend",
)
_NUMERIC_SIGNATURE_KEYS = frozenset(
    {
        "stl_scale_m_per_unit",
        "alpha_deg",
        "beta_or_bank_deg",
        "Tw_K",
        "ref_x_m",
        "ref_y_m",
        "ref_z_m",
        "Aref_m2",
        "Lref_Cl_m",
        "Lref_Cm_m",
        "Lref_Cn_m",
        "S",
        "Ti_K",
        "Mach",
        "Altitude_km",
        "shielding_on",
    }
)


def _no_legacy_payload_change(
    _data: dict[str, object],
    _row: Mapping[str, object],
    _paths: tuple[str, ...],
) -> None:
    return None


_LEGACY_SIGNATURE_POLICY = LegacySignaturePolicy(
    keys=_SIGNATURE_KEYS,
    numeric_keys=_NUMERIC_SIGNATURE_KEYS,
    compatibility_version=FMFSOLVER_COMPATIBILITY_VERSION,
    file_identity_style="fmf",
    signature_schema_version=2,
    adapt_payload=_no_legacy_payload_change,
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
        product_id="fmfsolver",
        window_title="Sentman FMF Solver (GUI)",
    )
