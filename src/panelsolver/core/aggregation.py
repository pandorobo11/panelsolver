"""Deterministic component aggregation and common result assembly."""

from __future__ import annotations

from collections.abc import Mapping

from ._validation import integer_scalar
from .contracts import (
    CommonCasePayload,
    CommonResults,
    ComponentResult,
    LocalLoads,
    ModelCasePayload,
    PanelFlowState,
    PanelGeometry,
    PayloadValue,
)
from .errors import ContractValueError
from .integration import (
    PanelIntegration,
    _integrated_coefficients,
    integrate_panel_loads,
)


def aggregate_component_results(
    geometry: PanelGeometry,
    flow_state: PanelFlowState,
    integration: PanelIntegration,
    case: CommonCasePayload,
    *,
    metadata_by_component: Mapping[int, Mapping[str, PayloadValue]] | None = None,
) -> tuple[ComponentResult, ...]:
    """Aggregate face contributions in ascending component-ID order."""
    if not isinstance(geometry, PanelGeometry):
        raise ContractValueError(
            "aggregate_component_results.geometry",
            "must be a PanelGeometry instance",
        )
    if not isinstance(flow_state, PanelFlowState):
        raise ContractValueError(
            "aggregate_component_results.flow_state",
            "must be a PanelFlowState instance",
        )
    if not isinstance(integration, PanelIntegration):
        raise ContractValueError(
            "aggregate_component_results.integration",
            "must be a PanelIntegration instance",
        )
    if not isinstance(case, CommonCasePayload):
        raise ContractValueError(
            "aggregate_component_results.case",
            "must be a CommonCasePayload instance",
        )
    if flow_state.n_faces != geometry.n_faces:
        raise ContractValueError(
            "aggregate_component_results.flow_state",
            "panel count must match geometry",
        )
    if integration.n_faces != geometry.n_faces:
        raise ContractValueError(
            "aggregate_component_results.integration",
            "panel count must match geometry",
        )

    metadata = _normalize_component_metadata(
        metadata_by_component,
        component_ids=geometry.unique_component_ids,
    )
    components: list[ComponentResult] = []
    for component_id in geometry.unique_component_ids:
        face_mask = geometry.component_ids == component_id
        force_coeff_stl = integration.face_force_coeff_stl[face_mask].sum(axis=0)
        moment_area_coeff_body_m = integration.face_moment_area_coeff_body_m[
            face_mask
        ].sum(axis=0)
        components.append(
            ComponentResult(
                component_id=component_id,
                integrated=_integrated_coefficients(
                    force_coeff_stl,
                    moment_area_coeff_body_m,
                    case,
                ),
                face_count=int(face_mask.sum()),
                shielded_face_count=int(flow_state.shielded[face_mask].sum()),
                metadata=metadata.get(component_id, {}),
            )
        )
    return tuple(components)


def assemble_common_results(
    case: CommonCasePayload,
    model_case: ModelCasePayload,
    geometry: PanelGeometry,
    flow_state: PanelFlowState,
    local_loads: LocalLoads,
    *,
    metadata: Mapping[str, PayloadValue] | None = None,
    metadata_by_component: Mapping[int, Mapping[str, PayloadValue]] | None = None,
) -> CommonResults:
    """Integrate panel loads and assemble the complete common result envelope."""
    integration = integrate_panel_loads(geometry, local_loads, case)
    components = aggregate_component_results(
        geometry,
        flow_state,
        integration,
        case,
        metadata_by_component=metadata_by_component,
    )
    return CommonResults(
        case=case,
        model_case=model_case,
        geometry=geometry,
        flow_state=flow_state,
        local_loads=local_loads,
        total=integration.total,
        components=components,
        metadata={} if metadata is None else metadata,
    )


def _normalize_component_metadata(
    value: Mapping[int, Mapping[str, PayloadValue]] | None,
    *,
    component_ids: tuple[int, ...],
) -> dict[int, Mapping[str, PayloadValue]]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ContractValueError(
            "metadata_by_component",
            "must be a mapping",
        )
    normalized: dict[int, Mapping[str, PayloadValue]] = {}
    for raw_component_id, item in value.items():
        component_id = integer_scalar(
            raw_component_id,
            field="metadata_by_component key",
            nonnegative=True,
        )
        if component_id in normalized:
            raise ContractValueError(
                "metadata_by_component",
                "component IDs must be unique",
            )
        normalized[component_id] = item
    unexpected = set(normalized) - set(component_ids)
    if unexpected:
        raise ContractValueError(
            "metadata_by_component",
            f"contains unknown component IDs {sorted(unexpected)}",
        )
    return normalized


__all__ = ("aggregate_component_results", "assemble_common_results")
