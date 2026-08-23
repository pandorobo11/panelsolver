"""Pinned Sentman free-molecular-flow model behind ``PanelLoadModel``."""

from __future__ import annotations

import math
from dataclasses import dataclass
from numbers import Real

import numpy as np
from scipy.special import erf

from panelsolver.core import (
    ContractValueError,
    LocalLoads,
    ModelCasePayload,
    PanelFlowState,
    PanelGeometry,
)

from .sentman_atmosphere import (
    altitude_range_km,
    mean_to_most_probable_speed,
    sample_at_altitude_km,
)

SENTMAN_MODEL_ID = "sentman"
SENTMAN_ALGORITHM_VERSION = "sentman-b62bc844"


class SentmanCaseError(ContractValueError):
    """A Sentman model payload violates its pinned physical-domain contract."""


@dataclass(frozen=True, slots=True)
class ResolvedSentmanCase:
    """Validated Sentman inputs after Mode A/B atmosphere resolution."""

    mode: str
    speed_ratio: float
    translational_temperature_k: float
    wall_temperature_k: float
    mach: float | None
    altitude_km: float | None

    @property
    def signature_payload(self) -> dict[str, None | float | str]:
        """Return a fresh model-only payload without choosing serialization."""
        return {
            "mode": self.mode,
            "S": self.speed_ratio if self.mode == "A" else None,
            "Ti_K": (
                self.translational_temperature_k if self.mode == "A" else None
            ),
            "Mach": self.mach,
            "Altitude_km": self.altitude_km,
            "Tw_K": self.wall_temperature_k,
        }


def _is_specified(value: object) -> bool:
    return value is not None and not (isinstance(value, str) and not value.strip())


def _positive_real(payload: ModelCasePayload, name: str) -> float:
    value = payload.payload.get(name)
    field = f"ModelCasePayload.payload.{name}"
    if isinstance(value, bool) or not isinstance(value, Real):
        raise SentmanCaseError(field, "must be a real scalar")
    result = float(value)
    if not math.isfinite(result):
        raise SentmanCaseError(field, "must be finite")
    if result <= 0.0:
        raise SentmanCaseError(field, "must be > 0")
    return result


def _nonnegative_real(payload: ModelCasePayload, name: str) -> float:
    value = payload.payload.get(name)
    field = f"ModelCasePayload.payload.{name}"
    if isinstance(value, bool) or not isinstance(value, Real):
        raise SentmanCaseError(field, "must be a real scalar")
    result = float(value)
    if not math.isfinite(result):
        raise SentmanCaseError(field, "must be finite")
    if result < 0.0:
        raise SentmanCaseError(field, "must be >= 0")
    return result


def resolve_sentman_case(case: ModelCasePayload) -> ResolvedSentmanCase:
    """Validate one model payload and resolve its exact legacy Mode A/B state."""
    if not isinstance(case, ModelCasePayload):
        raise SentmanCaseError("case", "must be a ModelCasePayload instance")
    if case.model_id != SENTMAN_MODEL_ID:
        raise SentmanCaseError(
            "ModelCasePayload.model_id",
            f"must be {SENTMAN_MODEL_ID!r}",
        )

    has_s = _is_specified(case.payload.get("S"))
    has_ti = _is_specified(case.payload.get("Ti_K"))
    has_mach = _is_specified(case.payload.get("Mach"))
    has_altitude = _is_specified(case.payload.get("Altitude_km"))
    if has_s != has_ti:
        raise SentmanCaseError(
            "ModelCasePayload.payload.S,Ti_K",
            "Mode A requires both 'S' and 'Ti_K'",
        )
    if has_mach != has_altitude:
        raise SentmanCaseError(
            "ModelCasePayload.payload.Mach,Altitude_km",
            "Mode B requires both 'Mach' and 'Altitude_km'",
        )
    mode_a = has_s and has_ti
    mode_b = has_mach and has_altitude
    if mode_a and mode_b:
        raise SentmanCaseError(
            "ModelCasePayload.payload.mode",
            "specify either Mode A or Mode B, not both",
        )
    if not mode_a and not mode_b:
        raise SentmanCaseError(
            "ModelCasePayload.payload.mode",
            "specify one complete mode (Mode A: S+Ti_K, Mode B: Mach+Altitude_km)",
        )

    wall_temperature_k = _positive_real(case, "Tw_K")
    if mode_a:
        speed_ratio = _positive_real(case, "S")
        translational_temperature_k = _positive_real(case, "Ti_K")
        return ResolvedSentmanCase(
            mode="A",
            speed_ratio=speed_ratio,
            translational_temperature_k=translational_temperature_k,
            wall_temperature_k=wall_temperature_k,
            mach=None,
            altitude_km=None,
        )

    mach = _positive_real(case, "Mach")
    altitude_km = _nonnegative_real(case, "Altitude_km")
    minimum, maximum = altitude_range_km()
    if altitude_km < minimum or altitude_km > maximum:
        raise SentmanCaseError(
            "ModelCasePayload.payload.Altitude_km",
            f"must be within [{minimum}, {maximum}] km",
        )
    atmosphere = sample_at_altitude_km(altitude_km)
    translational_temperature_k = atmosphere["T_K"]
    most_probable_speed_ms = mean_to_most_probable_speed(atmosphere["Vmean_ms"])
    speed_ratio = mach * atmosphere["c_ms"] / most_probable_speed_ms
    if not math.isfinite(speed_ratio) or speed_ratio <= 0.0:
        raise SentmanCaseError(
            "ResolvedSentmanCase.speed_ratio",
            "Mode B must produce a finite positive speed ratio",
        )
    return ResolvedSentmanCase(
        mode="B",
        speed_ratio=speed_ratio,
        translational_temperature_k=translational_temperature_k,
        wall_temperature_k=wall_temperature_k,
        mach=mach,
        altitude_km=altitude_km,
    )


class SentmanModel:
    """Thin adapter of the pinned vectorized Sentman equations."""

    model_id = SENTMAN_MODEL_ID
    algorithm_version = SENTMAN_ALGORITHM_VERSION

    def validate_case(self, case: ModelCasePayload) -> None:
        resolve_sentman_case(case)

    def signature_payload(
        self,
        case: ModelCasePayload,
    ) -> dict[str, None | float | str]:
        """Return model-only normalized fields for Phase 5 envelope assembly."""
        return dict(resolve_sentman_case(case).signature_payload)

    def evaluate(
        self,
        geometry: PanelGeometry,
        flow_state: PanelFlowState,
        case: ModelCasePayload,
    ) -> LocalLoads:
        if not isinstance(geometry, PanelGeometry):
            raise SentmanCaseError("geometry", "must be a PanelGeometry instance")
        if not isinstance(flow_state, PanelFlowState):
            raise SentmanCaseError(
                "flow_state",
                "must be a PanelFlowState instance",
            )
        if geometry.n_faces != flow_state.n_faces:
            raise SentmanCaseError(
                "flow_state",
                "panel count must match geometry",
            )
        resolved = resolve_sentman_case(case)
        traction = _sentman_traction_coefficients(
            velocity_hat_stl=flow_state.velocity_hat_stl,
            normals_out_stl=geometry.normals_out_stl,
            speed_ratio=resolved.speed_ratio,
            translational_temperature_k=resolved.translational_temperature_k,
            wall_temperature_k=resolved.wall_temperature_k,
            shielded=flow_state.shielded,
        )
        normal_dot_velocity = np.einsum(
            "ij,j->i",
            geometry.normals_out_stl,
            flow_state.velocity_hat_stl,
        )
        theta_deg = np.degrees(
            np.arccos(np.clip(normal_dot_velocity, -1.0, 1.0))
        )
        normal_traction_coeff = -np.einsum(
            "ij,ij->i",
            traction,
            geometry.normals_out_stl,
        )
        tangent_stl = (
            flow_state.velocity_hat_stl[None, :]
            - normal_dot_velocity[:, None] * geometry.normals_out_stl
        )
        tangent_norm = np.linalg.norm(tangent_stl, axis=1)
        tangent_hat_stl = np.zeros_like(tangent_stl)
        tangent_is_defined = tangent_norm > 1.0e-12
        tangent_hat_stl[tangent_is_defined] = (
            tangent_stl[tangent_is_defined]
            / tangent_norm[tangent_is_defined, None]
        )
        tangential_traction_coeff = np.einsum(
            "ij,ij->i",
            traction,
            tangent_hat_stl,
        )
        return LocalLoads(
            traction_coeff_stl=traction,
            cell_scalars={
                "normal_traction_coeff": normal_traction_coeff,
                "tangential_traction_coeff": tangential_traction_coeff,
                "theta_deg": theta_deg,
            },
            metadata={
                "mode": resolved.mode,
                "S": resolved.speed_ratio,
                "Ti_K": resolved.translational_temperature_k,
                "Tw_K": resolved.wall_temperature_k,
            },
        )


def _sentman_traction_coefficients(
    *,
    velocity_hat_stl: np.ndarray,
    normals_out_stl: np.ndarray,
    speed_ratio: float,
    translational_temperature_k: float,
    wall_temperature_k: float,
    shielded: np.ndarray,
) -> np.ndarray:
    """Return the legacy Sentman numerator at the Phase 2 model boundary.

    The legacy routine divides this vector by ``Aref``.  The common Phase 3
    integrator owns ``area/Aref``, so this adapter returns the unchanged
    numerator and does not duplicate reference-area normalization.
    """
    out = np.zeros((normals_out_stl.shape[0], 3), dtype=np.float64)
    active = ~shielded
    if not np.any(active):
        return out

    n_in = -normals_out_stl[active]
    gamma = n_in @ velocity_hat_stl
    hs = gamma * speed_ratio
    phi = 1.0 + np.asarray(erf(hs), dtype=float)
    exponential = np.exp(-(hs * hs))

    inverse_s = 1.0 / speed_ratio
    inverse_s_squared = inverse_s * inverse_s
    sqrt_pi = math.sqrt(math.pi)
    sqrt_wall_to_translation = math.sqrt(
        wall_temperature_k / translational_temperature_k
    )

    incident = gamma * phi + (inverse_s / sqrt_pi) * exponential
    normal_incident = 0.5 * inverse_s_squared * phi
    reflected = 0.5 * sqrt_wall_to_translation * (
        (gamma * sqrt_pi * inverse_s) * phi
        + inverse_s_squared * exponential
    )
    out[active] = (
        incident[:, None] * velocity_hat_stl[None, :]
        + (normal_incident + reflected)[:, None] * n_in
    )
    return out


def _helper_positive_real(value: object, *, field: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise SentmanCaseError(field, "must be a real scalar")
    result = float(value)
    if not math.isfinite(result):
        raise SentmanCaseError(field, "must be finite")
    if result <= 0.0:
        raise SentmanCaseError(field, "must be > 0")
    return result


def _helper_unit_array(
    value: object,
    *,
    field: str,
    shape: tuple[int | str, ...],
) -> np.ndarray:
    try:
        raw = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise SentmanCaseError(field, "must be a rectangular real array") from exc
    if raw.dtype.kind not in "iuf":
        raise SentmanCaseError(field, "must be a real array")
    array = np.asarray(raw, dtype=np.float64)
    if len(array.shape) != len(shape) or any(
        not isinstance(required, str) and actual != required
        for actual, required in zip(array.shape, shape, strict=True)
    ):
        raise SentmanCaseError(field, f"must have shape {shape}")
    if not np.isfinite(array).all():
        raise SentmanCaseError(field, "must contain only finite values")
    norms = np.hypot.reduce(np.abs(array), axis=-1)
    if not np.allclose(norms, 1.0, rtol=0.0, atol=1.0e-12):
        raise SentmanCaseError(field, "must contain unit vectors")
    return array


def _helper_shield_mask(value: object, *, n_faces: int) -> np.ndarray:
    if isinstance(value, (bool, np.bool_)):
        return np.full(n_faces, bool(value), dtype=np.bool_)
    try:
        mask = np.asarray(value)
    except (TypeError, ValueError) as exc:
        raise SentmanCaseError(
            "shielded", "must be a boolean scalar or rectangular array"
        ) from exc
    if mask.dtype.kind != "b" or mask.shape != (n_faces,):
        raise SentmanCaseError(
            "shielded", f"must be a boolean scalar or shape ({n_faces},)"
        )
    return np.asarray(mask, dtype=np.bool_)


def sentman_dC_dA_vectors(
    Vhat: np.ndarray,
    n_out: np.ndarray,
    S: float,
    Ti: float,
    Tw: float,
    Aref: float,
    shielded: np.ndarray | bool = False,
) -> np.ndarray:
    """Expose the pinned legacy Sentman density over the shared model formula."""
    reference_area = _helper_positive_real(Aref, field="Aref")
    speed_ratio = _helper_positive_real(S, field="S")
    translational_temperature = _helper_positive_real(Ti, field="Ti")
    wall_temperature = _helper_positive_real(Tw, field="Tw")
    velocity = _helper_unit_array(Vhat, field="Vhat", shape=(3,))
    normals = _helper_unit_array(n_out, field="n_out", shape=("N", 3))
    if normals.shape[0] == 0:
        raise SentmanCaseError("n_out", "must contain at least one panel normal")
    mask = _helper_shield_mask(shielded, n_faces=normals.shape[0])
    return _sentman_traction_coefficients(
        velocity_hat_stl=velocity,
        normals_out_stl=normals,
        speed_ratio=speed_ratio,
        translational_temperature_k=translational_temperature,
        wall_temperature_k=wall_temperature,
        shielded=mask,
    ) / reference_area


def sentman_dC_dA_vector(
    Vhat: np.ndarray,
    n_out: np.ndarray,
    S: float,
    Ti: float,
    Tw: float,
    Aref: float,
    shielded: bool = False,
) -> np.ndarray:
    """Scalar-panel compatibility form of :func:`sentman_dC_dA_vectors`."""
    normal = _helper_unit_array(n_out, field="n_out", shape=(3,))
    return sentman_dC_dA_vectors(
        Vhat,
        normal[None, :],
        S,
        Ti,
        Tw,
        Aref,
        shielded,
    )[0]


__all__ = (
    "SENTMAN_ALGORITHM_VERSION",
    "SENTMAN_MODEL_ID",
    "ResolvedSentmanCase",
    "SentmanCaseError",
    "SentmanModel",
    "resolve_sentman_case",
    "sentman_dC_dA_vector",
    "sentman_dC_dA_vectors",
)
