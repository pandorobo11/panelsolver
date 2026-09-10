"""Pinned hypersonic pressure models behind ``PanelLoadModel``."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real

import numpy as np

from panelsolver.core import (
    ContractValueError,
    LocalLoads,
    ModelCasePayload,
    PanelFlowState,
    PanelGeometry,
    SchedulingAffinityHint,
)

from .modified_newtonian import modified_newtonian_cp_max
from .prandtl_meyer import prandtl_meyer_pressure_coefficient
from .selectors import (
    normalize_leeward_equation,
    normalize_windward_equation,
    split_semicolon_tokens,
)
from .tangent_cone import tangent_cone_pressure_coefficient
from .tangent_wedge import tangent_wedge_pressure_coefficient

HYPERSONIC_MODEL_ID = "hypersonic"
HYPERSONIC_ALGORITHM_VERSION = "hypersonic-dc1357d0"
_TANGENT_CONE_AFFINITY_PRIORITY = 2
_TANGENT_WEDGE_AFFINITY_PRIORITY = 1


class HypersonicCaseError(ContractValueError):
    """A hypersonic payload violates its pinned physical-domain contract."""


@dataclass(frozen=True, slots=True)
class ResolvedHypersonicCase:
    """Validated Mach state and independent surface-equation selectors."""

    mach: float
    gamma: float
    windward_equations: tuple[str, ...]
    leeward_equations: tuple[str, ...]

    @property
    def windward_selector_text(self) -> str:
        return ";".join(self.windward_equations)

    @property
    def leeward_selector_text(self) -> str:
        return ";".join(self.leeward_equations)

    @property
    def signature_payload(self) -> dict[str, float | str]:
        """Return fresh model-only fields without choosing serialization."""
        return {
            "Mach": self.mach,
            "gamma": self.gamma,
            "windward_eq": self.windward_selector_text,
            "leeward_eq": self.leeward_selector_text,
        }


def _real(payload: ModelCasePayload, name: str) -> float:
    value = payload.payload.get(name)
    field = f"ModelCasePayload.payload.{name}"
    if isinstance(value, bool) or not isinstance(value, Real):
        raise HypersonicCaseError(field, "must be a real scalar")
    result = float(value)
    if not math.isfinite(result):
        raise HypersonicCaseError(field, "must be finite")
    return result


def _normalize_equation_selectors(
    value: object,
    *,
    field: str,
    default: str,
    normalizer,
) -> tuple[str, ...]:
    if value is not None and not isinstance(value, str):
        raise HypersonicCaseError(field, "must be a semicolon-separated string")
    tokens = split_semicolon_tokens(value)
    if not tokens:
        tokens = [default]
    elif any(token == "" for token in tokens):
        raise HypersonicCaseError(field, "must not contain empty ';' entries")
    try:
        return tuple(normalizer(token) for token in tokens)
    except ValueError as exc:
        raise HypersonicCaseError(field, str(exc)) from exc


def resolve_hypersonic_case(case: ModelCasePayload) -> ResolvedHypersonicCase:
    """Validate one model payload without importing common execution policy."""
    if not isinstance(case, ModelCasePayload):
        raise HypersonicCaseError("case", "must be a ModelCasePayload instance")
    if case.model_id != HYPERSONIC_MODEL_ID:
        raise HypersonicCaseError(
            "ModelCasePayload.model_id",
            f"must be {HYPERSONIC_MODEL_ID!r}",
        )

    mach = _real(case, "Mach")
    gamma = _real(case, "gamma")
    if mach <= 0.0:
        raise HypersonicCaseError("ModelCasePayload.payload.Mach", "must be > 0")
    if gamma <= 1.0:
        raise HypersonicCaseError(
            "ModelCasePayload.payload.gamma",
            "must be > 1",
        )
    windward = _normalize_equation_selectors(
        case.payload.get("windward_eq"),
        field="ModelCasePayload.payload.windward_eq",
        default="newtonian",
        normalizer=normalize_windward_equation,
    )
    leeward = _normalize_equation_selectors(
        case.payload.get("leeward_eq"),
        field="ModelCasePayload.payload.leeward_eq",
        default="shield",
        normalizer=normalize_leeward_equation,
    )
    if mach <= 1.0:
        supersonic_windward = {
            "modified_newtonian",
            "tangent_wedge",
            "tangent_cone",
        }
        selected = supersonic_windward.intersection(windward)
        if selected:
            equation = next(eq for eq in windward if eq in selected)
            raise HypersonicCaseError(
                "ModelCasePayload.payload.Mach",
                f"must be > 1 when windward_eq={equation}",
            )
        if "prandtl_meyer" in leeward:
            raise HypersonicCaseError(
                "ModelCasePayload.payload.Mach",
                "must be > 1 when leeward_eq=prandtl_meyer",
            )
    return ResolvedHypersonicCase(
        mach=mach,
        gamma=gamma,
        windward_equations=windward,
        leeward_equations=leeward,
    )


def _expand_for_components(
    equations: tuple[str, ...],
    component_ids: tuple[int, ...],
    *,
    field: str,
) -> dict[int, str]:
    if len(equations) == 1:
        return {component_id: equations[0] for component_id in component_ids}
    if len(equations) != len(component_ids):
        raise HypersonicCaseError(
            field,
            f"must have 1 entry or {len(component_ids)} entries "
            f"(to match geometry components), got {len(equations)}",
        )
    return dict(zip(component_ids, equations, strict=True))


class HypersonicModel:
    """Hypersonic pressure-only panel-load model."""

    model_id = HYPERSONIC_MODEL_ID
    algorithm_version = HYPERSONIC_ALGORITHM_VERSION

    def validate_case(self, case: ModelCasePayload) -> None:
        resolve_hypersonic_case(case)

    def signature_payload(self, case: ModelCasePayload) -> dict[str, float | str]:
        """Return normalized model-case fields for the canonical signature envelope."""
        return dict(resolve_hypersonic_case(case).signature_payload)

    def scheduling_affinities(
        self,
        case: ModelCasePayload,
    ) -> tuple[SchedulingAffinityHint, ...]:
        """Describe likely process-local cache reuse as performance-only hints."""
        resolved = resolve_hypersonic_case(case)
        selected = set(resolved.windward_equations)
        hints: list[SchedulingAffinityHint] = []
        if "tangent_cone" in selected:
            hints.append(
                SchedulingAffinityHint(
                    ("tangent_cone", resolved.mach, resolved.gamma),
                    _TANGENT_CONE_AFFINITY_PRIORITY,
                )
            )
        if "tangent_wedge" in selected:
            hints.append(
                SchedulingAffinityHint(
                    ("tangent_wedge", resolved.mach, resolved.gamma),
                    _TANGENT_WEDGE_AFFINITY_PRIORITY,
                )
            )
        return tuple(hints)

    def evaluate(
        self,
        geometry: PanelGeometry,
        flow_state: PanelFlowState,
        case: ModelCasePayload,
    ) -> LocalLoads:
        if not isinstance(geometry, PanelGeometry):
            raise HypersonicCaseError("geometry", "must be a PanelGeometry instance")
        if not isinstance(flow_state, PanelFlowState):
            raise HypersonicCaseError(
                "flow_state",
                "must be a PanelFlowState instance",
            )
        if geometry.n_faces != flow_state.n_faces:
            raise HypersonicCaseError(
                "flow_state",
                "panel count must match geometry",
            )

        resolved = resolve_hypersonic_case(case)
        component_ids = geometry.unique_component_ids
        windward_by_component = _expand_for_components(
            resolved.windward_equations,
            component_ids,
            field="ModelCasePayload.payload.windward_eq",
        )
        leeward_by_component = _expand_for_components(
            resolved.leeward_equations,
            component_ids,
            field="ModelCasePayload.payload.leeward_eq",
        )
        cp_max = (
            modified_newtonian_cp_max(resolved.mach, resolved.gamma)
            if any(
                equation in {"modified_newtonian", "tangent_wedge", "tangent_cone"}
                for equation in resolved.windward_equations
            )
            else 2.0
        )
        traction, cp = _pressure_traction_coefficients(
            velocity_hat_stl=flow_state.velocity_hat_stl,
            normals_out_stl=geometry.normals_out_stl,
            component_ids=geometry.component_ids,
            shielded=flow_state.shielded,
            mach=resolved.mach,
            gamma=resolved.gamma,
            cp_max=cp_max,
            windward_by_component=windward_by_component,
            leeward_by_component=leeward_by_component,
        )
        normal_dot_velocity = np.einsum(
            "ij,j->i",
            geometry.normals_out_stl,
            flow_state.velocity_hat_stl,
        )
        theta_deg = np.degrees(np.arccos(np.clip(normal_dot_velocity, -1.0, 1.0)))
        return LocalLoads(
            traction_coeff_stl=traction,
            cell_scalars={"cp": cp, "theta_deg": theta_deg},
            metadata={
                "Mach": resolved.mach,
                "gamma": resolved.gamma,
                "windward_eq": resolved.windward_selector_text,
                "leeward_eq": resolved.leeward_selector_text,
            },
        )


def _pressure_traction_coefficients(
    *,
    velocity_hat_stl: np.ndarray,
    normals_out_stl: np.ndarray,
    component_ids: np.ndarray,
    shielded: np.ndarray,
    mach: float,
    gamma: float,
    cp_max: float,
    windward_by_component: dict[int, str],
    leeward_by_component: dict[int, str],
) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate pinned pressure branches and adapt out legacy ``/Aref``."""
    n_faces = normals_out_stl.shape[0]
    traction = np.zeros((n_faces, 3), dtype=np.float64)
    cp = np.zeros(n_faces, dtype=np.float64)
    active = ~shielded
    if not np.any(active):
        return traction, cp

    n_in = -normals_out_stl[active]
    incidence_cosine = n_in @ velocity_hat_stl
    active_indices = np.flatnonzero(active)
    active_components = component_ids[active_indices]
    for component_id, windward_equation in windward_by_component.items():
        local = active_components == component_id
        if not np.any(local):
            continue
        incidence = incidence_cosine[local]
        cp_local = np.zeros_like(incidence)
        windward = incidence > 0.0
        if windward_equation == "newtonian":
            cp_local[windward] = 2.0 * np.square(incidence[windward])
        elif windward_equation == "modified_newtonian":
            cp_local[windward] = cp_max * np.square(incidence[windward])
        elif windward_equation == "tangent_wedge":
            turning = np.arcsin(np.clip(incidence[windward], -1.0, 1.0))
            cp_local[windward] = tangent_wedge_pressure_coefficient(
                Mach=mach,
                gamma=gamma,
                deltar=turning,
                cp_cap=cp_max,
            )
        else:
            turning = np.arcsin(np.clip(incidence[windward], -1.0, 1.0))
            cp_local[windward] = tangent_cone_pressure_coefficient(
                Mach=mach,
                gamma=gamma,
                deltar=turning,
                cp_cap=cp_max,
            )

        if leeward_by_component[component_id] == "prandtl_meyer":
            leeward = ~windward
            turning = np.arcsin(np.clip(incidence[leeward], -1.0, 1.0))
            cp_local[leeward] = prandtl_meyer_pressure_coefficient(
                Mach=mach,
                gamma=gamma,
                deltar=turning,
            )
        local_indices = active_indices[local]
        cp[local_indices] = cp_local

    nonzero = np.abs(cp) > 0.0
    if np.any(nonzero):
        traction[nonzero] = -cp[nonzero, None] * normals_out_stl[nonzero]
    return traction, cp


__all__ = (
    "HYPERSONIC_ALGORITHM_VERSION",
    "HYPERSONIC_MODEL_ID",
    "HypersonicCaseError",
    "HypersonicModel",
    "ResolvedHypersonicCase",
    "resolve_hypersonic_case",
)
