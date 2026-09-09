"""Model-independent panel force and moment integration."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ._validation import float_array, require_nonempty_faces
from .contracts import (
    CommonCasePayload,
    IntegratedCoefficients,
    LocalLoads,
    PanelGeometry,
)
from .errors import ContractValueError
from .frames import body_to_stability, stl_to_body


@dataclass(frozen=True, slots=True, eq=False)
class PanelIntegration:
    """Immutable per-face contributions and their integrated total."""

    face_force_coeff_stl: np.ndarray
    face_moment_area_coeff_body_m: np.ndarray
    total: IntegratedCoefficients

    def __post_init__(self) -> None:
        face_force = float_array(
            self.face_force_coeff_stl,
            field="PanelIntegration.face_force_coeff_stl",
            shape=("n_faces", 3),
        )
        require_nonempty_faces(
            face_force.shape[0],
            field="PanelIntegration.face_force_coeff_stl",
        )
        face_moment = float_array(
            self.face_moment_area_coeff_body_m,
            field="PanelIntegration.face_moment_area_coeff_body_m",
            shape=(face_force.shape[0], 3),
        )
        if not isinstance(self.total, IntegratedCoefficients):
            raise ContractValueError(
                "PanelIntegration.total",
                "must be an IntegratedCoefficients instance",
            )
        object.__setattr__(self, "face_force_coeff_stl", face_force)
        object.__setattr__(
            self,
            "face_moment_area_coeff_body_m",
            face_moment,
        )

    @property
    def n_faces(self) -> int:
        return self.face_force_coeff_stl.shape[0]


def integrate_panel_loads(
    geometry: PanelGeometry,
    local_loads: LocalLoads,
    case: CommonCasePayload,
) -> PanelIntegration:
    """Apply common area/reference normalization and integrate one case."""
    if not isinstance(geometry, PanelGeometry):
        raise ContractValueError(
            "integrate_panel_loads.geometry",
            "must be a PanelGeometry instance",
        )
    if not isinstance(local_loads, LocalLoads):
        raise ContractValueError(
            "integrate_panel_loads.local_loads",
            "must be a LocalLoads instance",
        )
    if not isinstance(case, CommonCasePayload):
        raise ContractValueError(
            "integrate_panel_loads.case",
            "must be a CommonCasePayload instance",
        )
    if local_loads.n_faces != geometry.n_faces:
        raise ContractValueError(
            "integrate_panel_loads.local_loads",
            "panel count must match geometry",
        )

    area_scale = geometry.areas_m2 / case.Aref_m2
    face_force_coeff_stl = local_loads.traction_coeff_stl * area_scale[:, None]
    force_coeff_stl = face_force_coeff_stl.sum(axis=0)
    centers_body_m = stl_to_body(geometry.centers_stl_m)
    reference_body_m = stl_to_body(case.moment_reference_stl_m)
    face_force_coeff_body = stl_to_body(face_force_coeff_stl)
    face_moment_area_coeff_body_m = np.cross(
        centers_body_m - reference_body_m[None, :],
        face_force_coeff_body,
    )
    moment_area_coeff_body_m = face_moment_area_coeff_body_m.sum(axis=0)
    total = _integrated_coefficients(
        force_coeff_stl,
        moment_area_coeff_body_m,
        case,
    )
    return PanelIntegration(
        face_force_coeff_stl=face_force_coeff_stl,
        face_moment_area_coeff_body_m=face_moment_area_coeff_body_m,
        total=total,
    )


def _integrated_coefficients(
    force_coeff_stl: np.ndarray,
    moment_area_coeff_body_m: np.ndarray,
    case: CommonCasePayload,
) -> IntegratedCoefficients:
    force_coeff_body = stl_to_body(force_coeff_stl)
    force_coeff_stability = body_to_stability(
        force_coeff_body,
        alpha_stability_deg=case.alpha_stability_deg,
    )
    moment_coeff_body = moment_area_coeff_body_m / np.array(
        [case.Lref_Cl_m, case.Lref_Cm_m, case.Lref_Cn_m],
        dtype=np.float64,
    )
    return IntegratedCoefficients(
        force_coeff_stl=force_coeff_stl,
        force_coeff_body=force_coeff_body,
        force_coeff_stability=force_coeff_stability,
        moment_area_coeff_body_m=moment_area_coeff_body_m,
        moment_coeff_body=moment_coeff_body,
    )


__all__ = ("PanelIntegration", "integrate_panel_loads")
